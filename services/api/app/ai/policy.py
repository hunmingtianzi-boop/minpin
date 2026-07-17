"""Deterministic input safety, evidence gating, and quotation controls."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Sequence

from .schemas import Refusal, RefusalCode, RetrievedEvidence, StructuredModelAnswer


class PolicyFlag(StrEnum):
    PROMPT_INJECTION = "prompt_injection"
    SENSITIVE_DATA = "sensitive_data"
    HIGH_RISK = "high_risk"
    PRICING = "pricing"


@dataclass(frozen=True, slots=True)
class InputPolicyDecision:
    normalized_text: str
    flags: tuple[PolicyFlag, ...]
    refusal: Refusal | None = None

    @property
    def blocked(self) -> bool:
        return self.refusal is not None


@dataclass(frozen=True, slots=True)
class InputSecurityConfig:
    max_chars: int = 4000

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be positive")


_INJECTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|rules|prompts)",
        r"(?:reveal|show|print|repeat|dump).{0,50}(?:system|developer)\s+(?:prompt|message|instructions)",
        r"(?:act\s+as|enable)\s+(?:dan|developer\s+mode|jailbreak)",
        r"忽略.{0,20}(?:之前|以上|先前).{0,20}(?:指令|规则|提示词)",
        r"(?:显示|输出|复述|泄露|告诉我).{0,40}(?:系统提示词|开发者指令|隐藏指令)",
        r"(?:越狱|开发者模式|无视安全规则)",
    )
)

_SENSITIVE_DATA_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bsk-[A-Za-z0-9_-]{12,}\b",
        r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"(?:api[_ -]?key|访问密钥|私钥|密码).{0,15}(?:是|:|=)\s*\S{8,}",
    )
)

_HIGH_RISK_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:保证|承诺).{0,12}(?:收益|回报|效果|通过|成交)",
        r"(?:保本|稳赚|零风险|最终法律意见|代签合同)",
        r"(?:诊断|处方|用药剂量|停药建议)",
        r"(?:guaranteed return|risk[- ]free|medical diagnosis|legal conclusion)",
    )
)

_PRICING_PATTERN = re.compile(
    r"(?:报价|价格|多少钱|费用|收费|折扣|优惠|套餐|price|pricing|quote|cost|discount)",
    re.IGNORECASE,
)

_PRICING_EVIDENCE_PATTERN = re.compile(
    r"(?:[¥￥$]\s*\d|(?:USD|CNY|RMB)\s*\d|\d[\d,.]*\s*(?:元|万元|人民币|美元|/月|/年|每月|每年)|报价|价格|套餐)",
    re.IGNORECASE,
)

_MONEY_CLAIM_PATTERN = re.compile(
    r"(?:[¥￥$]\s*\d[\d,]*(?:\.\d+)?(?:\s*/(?:月|年))?"
    r"|(?:USD|CNY|RMB)\s*\d[\d,]*(?:\.\d+)?(?:\s*/(?:month|year))?"
    r"|\d[\d,]*(?:\.\d+)?\s*(?:万元|元|人民币|美元)(?:\s*/(?:月|年))?"
    r"|\d[\d,]*(?:\.\d+)?\s*(?:每月|每年))",
    re.IGNORECASE,
)


class InputSecurityPolicy:
    def __init__(self, config: InputSecurityConfig | None = None) -> None:
        self.config = config or InputSecurityConfig()

    def evaluate(self, text: str) -> InputPolicyDecision:
        normalized = _normalize_input(text)
        if not normalized:
            return InputPolicyDecision(
                normalized_text="",
                flags=(),
                refusal=Refusal(
                    code=RefusalCode.INPUT_INVALID,
                    reason="问题不能为空。",
                    safe_alternative="请重新输入一个具体问题。",
                ),
            )
        if len(normalized) > self.config.max_chars:
            return InputPolicyDecision(
                normalized_text="",
                flags=(),
                refusal=Refusal(
                    code=RefusalCode.INPUT_INVALID,
                    reason="问题长度超过允许范围。",
                    safe_alternative="请缩短问题后重试。",
                ),
            )

        flags: list[PolicyFlag] = []
        if any(pattern.search(normalized) for pattern in _SENSITIVE_DATA_PATTERNS):
            flags.append(PolicyFlag.SENSITIVE_DATA)
            return InputPolicyDecision(
                normalized_text="",
                flags=tuple(flags),
                refusal=Refusal(
                    code=RefusalCode.SENSITIVE_DATA_REQUEST,
                    reason="请勿在问答中提交密钥、密码或私钥等敏感凭据。",
                    safe_alternative="请删除敏感值后重新描述需求。",
                ),
            )
        if any(pattern.search(normalized) for pattern in _INJECTION_PATTERNS):
            flags.append(PolicyFlag.PROMPT_INJECTION)
            return InputPolicyDecision(
                normalized_text="",
                flags=tuple(flags),
                refusal=Refusal(
                    code=RefusalCode.PROMPT_INJECTION,
                    reason="该请求试图改变系统规则或获取隐藏指令，无法处理。",
                    safe_alternative="可以直接询问已发布的企业、产品或服务信息。",
                ),
            )
        if any(pattern.search(normalized) for pattern in _HIGH_RISK_PATTERNS):
            flags.append(PolicyFlag.HIGH_RISK)
        if _PRICING_PATTERN.search(normalized):
            flags.append(PolicyFlag.PRICING)
        return InputPolicyDecision(normalized_text=normalized, flags=tuple(flags))


@dataclass(frozen=True, slots=True)
class EvidenceGateConfig:
    min_score: float = 0.0
    min_vector_score: float | None = None
    min_lexical_score: float | None = None
    max_evidence: int = 8
    high_risk_min_evidence: int = 2
    allow_general_answers_without_evidence: bool = False

    def __post_init__(self) -> None:
        if self.max_evidence <= 0 or self.high_risk_min_evidence <= 0:
            raise ValueError("evidence limits must be positive")
        if self.min_vector_score is not None and not -1 <= self.min_vector_score <= 1:
            raise ValueError("min_vector_score must be between -1 and 1")
        if self.min_lexical_score is not None and not 0 <= self.min_lexical_score <= 1:
            raise ValueError("min_lexical_score must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class EvidenceGateDecision:
    evidence: tuple[RetrievedEvidence, ...]
    refusal: Refusal | None
    needs_human_review: bool = False
    general_answer_allowed: bool = False

    @property
    def allowed(self) -> bool:
        return self.refusal is None


@dataclass(frozen=True, slots=True)
class OutputGateDecision:
    evidence: tuple[RetrievedEvidence, ...]
    refusal: Refusal | None
    needs_human_review: bool = False

    @property
    def allowed(self) -> bool:
        return self.refusal is None


class EvidenceGate:
    """Require published evidence before generation and validate claims after it."""

    def __init__(self, config: EvidenceGateConfig | None = None) -> None:
        self.config = config or EvidenceGateConfig()

    def before_generation(
        self,
        decision: InputPolicyDecision,
        evidence: Sequence[RetrievedEvidence],
    ) -> EvidenceGateDecision:
        accepted = tuple(
            item
            for item in sorted(evidence, key=lambda item: item.score, reverse=True)
            if self._score_allowed(item) and item.text.strip()
        )[: self.config.max_evidence]
        flags = set(decision.flags)
        if not accepted:
            if self.allows_general_answer(decision):
                return EvidenceGateDecision(
                    evidence=(),
                    refusal=None,
                    general_answer_allowed=True,
                )
            return EvidenceGateDecision(
                evidence=(),
                refusal=Refusal(
                    code=RefusalCode.INSUFFICIENT_EVIDENCE,
                    reason="当前已发布资料中没有足够证据回答该问题。",
                    safe_alternative="请补充问题细节，或联系企业工作人员确认。",
                ),
            )

        if PolicyFlag.PRICING in flags and not any(
            _has_pricing_evidence(item) for item in accepted
        ):
            return EvidenceGateDecision(
                evidence=accepted,
                refusal=Refusal(
                    code=RefusalCode.UNVERIFIED_PRICING,
                    reason="已发布资料中没有可核验的报价信息。",
                    safe_alternative="请联系企业工作人员获取正式报价。",
                ),
                needs_human_review=True,
            )

        authoritative = any(bool(item.metadata.get("authoritative")) for item in accepted)
        if (
            PolicyFlag.HIGH_RISK in flags
            and len(accepted) < self.config.high_risk_min_evidence
            and not authoritative
        ):
            return EvidenceGateDecision(
                evidence=accepted,
                refusal=Refusal(
                    code=RefusalCode.HIGH_RISK_UNSUPPORTED,
                    reason="该高风险问题缺少足够的权威资料支持。",
                    safe_alternative="请转交具备授权的工作人员复核。",
                ),
                needs_human_review=True,
            )
        return EvidenceGateDecision(
            evidence=accepted,
            refusal=None,
            needs_human_review=PolicyFlag.HIGH_RISK in flags,
            general_answer_allowed=(
                self.allows_general_answer(decision)
            ),
        )

    def allows_general_answer(self, decision: InputPolicyDecision) -> bool:
        flags = set(decision.flags)
        return (
            self.config.allow_general_answers_without_evidence
            and PolicyFlag.PRICING not in flags
            and PolicyFlag.HIGH_RISK not in flags
        )

    def _score_allowed(self, item: RetrievedEvidence) -> bool:
        if item.score < self.config.min_score:
            return False
        configured_threshold = False
        threshold_passed = False
        if self.config.min_vector_score is not None and item.vector_score is not None:
            configured_threshold = True
            threshold_passed = threshold_passed or item.vector_score >= self.config.min_vector_score
        if self.config.min_lexical_score is not None and item.lexical_score is not None:
            configured_threshold = True
            threshold_passed = (
                threshold_passed or item.lexical_score >= self.config.min_lexical_score
            )
        return threshold_passed if configured_threshold else True

    def after_generation(
        self,
        decision: InputPolicyDecision,
        output: StructuredModelAnswer,
        evidence: Sequence[RetrievedEvidence],
    ) -> OutputGateDecision:
        if output.refusal_reason:
            return OutputGateDecision(
                evidence=(),
                refusal=Refusal(
                    code=RefusalCode.MODEL_REFUSAL,
                    reason=output.refusal_reason,
                    safe_alternative="请补充问题细节或联系企业工作人员。",
                ),
                needs_human_review=output.needs_human_review,
            )

        flags = set(decision.flags)
        by_id = {item.evidence_id: item for item in evidence}
        requested = tuple(output.cited_evidence_ids)
        if not requested:
            if self.allows_general_answer(decision):
                return OutputGateDecision(evidence=(), refusal=None)
            return OutputGateDecision(
                evidence=(),
                refusal=Refusal(
                    code=RefusalCode.UNGROUNDED_OUTPUT,
                    reason="模型回答未能通过来源一致性校验。",
                    safe_alternative="请稍后重试或联系企业工作人员。",
                ),
                needs_human_review=True,
            )
        if any(evidence_id not in by_id for evidence_id in requested):
            if self.allows_general_answer(decision):
                # For ordinary chat, an invalid optional citation must not hide
                # an otherwise useful model answer. Keep only verified ids.
                return OutputGateDecision(
                    evidence=tuple(
                        by_id[evidence_id]
                        for evidence_id in requested
                        if evidence_id in by_id
                    ),
                    refusal=None,
                )
            return OutputGateDecision(
                evidence=(),
                refusal=Refusal(
                    code=RefusalCode.UNGROUNDED_OUTPUT,
                    reason="模型回答未能通过来源一致性校验。",
                    safe_alternative="请稍后重试或联系企业工作人员。",
                ),
                needs_human_review=True,
            )
        cited = tuple(by_id[evidence_id] for evidence_id in requested)

        if PolicyFlag.PRICING in flags:
            unsupported = _unsupported_money_claims(output.answer, cited)
            if unsupported:
                return OutputGateDecision(
                    evidence=cited,
                    refusal=Refusal(
                        code=RefusalCode.UNVERIFIED_PRICING,
                        reason="回答包含未在引用资料中核验的金额，已阻止输出。",
                        safe_alternative="请联系企业工作人员获取正式报价。",
                    ),
                    needs_human_review=True,
                )

        return OutputGateDecision(
            evidence=cited,
            refusal=None,
            needs_human_review=(
                output.needs_human_review or PolicyFlag.HIGH_RISK in flags
            ),
        )


def _normalize_input(text: str) -> str:
    if not isinstance(text, str):
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = "".join(
        character
        for character in normalized
        if character in {"\n", "\t"} or unicodedata.category(character) != "Cc"
    )
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _has_pricing_evidence(evidence: RetrievedEvidence) -> bool:
    if str(evidence.metadata.get("content_type", "")).lower() in {
        "pricing",
        "price_list",
        "quotation",
        "offer",
    }:
        return True
    return bool(_PRICING_EVIDENCE_PATTERN.search(evidence.text))


def _unsupported_money_claims(
    answer: str,
    evidence: Sequence[RetrievedEvidence],
) -> tuple[str, ...]:
    claims = tuple(dict.fromkeys(match.group(0) for match in _MONEY_CLAIM_PATTERN.finditer(answer)))
    if not claims:
        return ()
    source = _compact("\n".join(item.text for item in evidence))
    return tuple(claim for claim in claims if _compact(claim) not in source)


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()
