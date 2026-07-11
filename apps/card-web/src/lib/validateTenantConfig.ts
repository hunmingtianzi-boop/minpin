export type TenantValidationErrorCode =
  | "invalid-config"
  | "invalid-required-field"
  | "invalid-slug"
  | "invalid-title-lines"
  | "invalid-media"
  | "invalid-theme"
  | "too-many-actions"
  | "too-many-metrics"
  | "duplicate-section-id"
  | "invalid-section-id"
  | "invalid-section-type"
  | "too-many-nav-items"
  | "invalid-item-count"
  | "invalid-faq-reference"
  | "invalid-knowledge-reference"
  | "invalid-knowledge-id"
  | "duplicate-knowledge-id"
  | "invalid-action-target";

export type TenantValidationError = {
  code: TenantValidationErrorCode;
  path: string;
  message: string;
};

export type TenantValidationResult = {
  valid: boolean;
  errors: TenantValidationError[];
};

type UnknownRecord = Record<string, unknown>;

const knownSectionTypes = new Set([
  "feature-grid",
  "media-showcase",
  "process",
  "evidence",
  "engagement",
  "faq",
  "closing",
]);

const themeTokenKeys = [
  "accent",
  "accentStrong",
  "accentSoft",
  "background",
  "surface",
  "surfaceRaised",
  "surfaceMuted",
  "text",
  "textSoft",
  "textFaint",
  "line",
  "lineStrong",
  "shadow",
] as const;

const assistantLabelKeys = [
  "closeBackdrop",
  "closeButton",
  "quickQuestions",
  "quickQuestionsIntro",
  "loading",
  "input",
  "placeholder",
  "send",
  "sourcePrefix",
] as const;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isNonEmptyString = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;

const isValidExternalTarget = (target: string) => {
  try {
    const url = new URL(target);
    return ["http:", "https:", "mailto:", "tel:"].includes(url.protocol);
  } catch {
    return false;
  }
};

const isValidActionTarget = (action: UnknownRecord) => {
  if (!isNonEmptyString(action.target)) return false;

  if (action.kind === "anchor") {
    return /^#[A-Za-z][A-Za-z0-9:_-]*$/.test(action.target);
  }

  if (action.kind === "external") {
    return isValidExternalTarget(action.target);
  }

  if (action.kind === "assistant") {
    return action.target.trim().length <= 160;
  }

  return false;
};

export function validateTenantConfig(config: unknown): TenantValidationResult {
  const errors: TenantValidationError[] = [];
  const addError = (
    code: TenantValidationErrorCode,
    path: string,
    message: string,
  ) => errors.push({ code, path, message });

  const requireObject = (value: unknown, path: string) => {
    if (isRecord(value)) return value;
    addError(
      "invalid-config",
      path,
      "A required configuration object is missing or invalid.",
    );
    return undefined;
  };

  const requireString = (value: unknown, path: string) => {
    if (isNonEmptyString(value)) return true;
    addError(
      "invalid-required-field",
      path,
      "A required text field is missing or empty.",
    );
    return false;
  };

  const validateCount = (
    value: unknown,
    path: string,
    min = 2,
    max = 6,
  ) => {
    if (!Array.isArray(value) || value.length < min || value.length > max) {
      addError(
        "invalid-item-count",
        path,
        `This list must contain between ${min} and ${max} items.`,
      );
      return false;
    }
    return true;
  };

  const validateStringArray = (
    value: unknown,
    path: string,
    min = 2,
    max = 6,
  ) => {
    const validCount = validateCount(value, path, min, max);
    if (!Array.isArray(value)) return false;

    value.forEach((item, index) => {
      requireString(item, `${path}[${index}]`);
    });
    return validCount;
  };

  const validateAction = (
    value: unknown,
    path: string,
    requiredKind?: "anchor" | "external" | "assistant",
  ) => {
    if (
      !isRecord(value) ||
      !isNonEmptyString(value.label) ||
      (requiredKind !== undefined && value.kind !== requiredKind) ||
      !isValidActionTarget(value)
    ) {
      addError(
        "invalid-action-target",
        path,
        "Action label, kind, or target is invalid.",
      );
      return false;
    }
    return true;
  };

  const validateActionGroup = (value: unknown, path: string) => {
    if (!Array.isArray(value)) {
      addError("invalid-config", path, "Actions must be provided as an array.");
      return;
    }

    if (value.length > 2) {
      addError(
        "too-many-actions",
        path,
        "A call-to-action group can contain at most two actions.",
      );
    }

    value.forEach((action, index) => validateAction(action, `${path}[${index}]`));
  };

  const validateMedia = (value: unknown, path: string) => {
    if (!isRecord(value)) {
      addError("invalid-media", path, "A required media object is missing or invalid.");
      return false;
    }

    let valid = true;
    if (!isNonEmptyString(value.src)) {
      addError("invalid-media", `${path}.src`, "Media source is missing or invalid.");
      valid = false;
    }
    if (typeof value.alt !== "string") {
      addError("invalid-media", `${path}.alt`, "Media alternative text must be a string.");
      valid = false;
    }

    for (const dimension of ["width", "height"] as const) {
      const size = value[dimension];
      if (
        size !== undefined &&
        (typeof size !== "number" || !Number.isInteger(size) || size <= 0)
      ) {
        addError(
          "invalid-media",
          `${path}.${dimension}`,
          "Media dimensions must be positive integers when provided.",
        );
        valid = false;
      }
    }

    return valid;
  };

  const validateItemObjects = (
    value: unknown,
    path: string,
    fields: readonly string[],
    min = 2,
    max = 6,
  ) => {
    validateCount(value, path, min, max);
    if (!Array.isArray(value)) return;

    value.forEach((item, index) => {
      if (!isRecord(item)) {
        addError(
          "invalid-config",
          `${path}[${index}]`,
          "List items must be configuration objects.",
        );
        return;
      }
      fields.forEach((field) => requireString(item[field], `${path}[${index}].${field}`));
    });
  };

  if (!isRecord(config)) {
    addError("invalid-config", "$", "Tenant config must be an object.");
    return { valid: false, errors };
  }

  if (
    !isNonEmptyString(config.id) ||
    !/^[a-z0-9][a-z0-9_-]{0,62}$/.test(config.id)
  ) {
    addError(
      "invalid-slug",
      "id",
      "Tenant slug must contain lowercase letters, digits, underscores, or hyphens.",
    );
  }
  requireString(config.version, "version");

  const seo = requireObject(config.seo, "seo");
  if (seo) {
    requireString(seo.title, "seo.title");
    requireString(seo.description, "seo.description");
  }

  const brand = requireObject(config.brand, "brand");
  if (brand) {
    for (const field of [
      "name",
      "shortName",
      "tagline",
      "headerDescriptor",
      "homeAriaLabel",
    ] as const) {
      requireString(brand[field], `brand.${field}`);
    }
    validateMedia(brand.logo, "brand.logo");
    validateAction(brand.officialAction, "brand.officialAction", "external");
  }

  const theme = requireObject(config.theme, "theme");
  if (theme) {
    if (!new Set(["system", "light", "dark"]).has(String(theme.defaultMode))) {
      addError("invalid-theme", "theme.defaultMode", "Theme mode is not supported.");
    }
    for (const field of [
      "action",
      "onAction",
      "radiusCard",
      "radiusControl",
      "radiusSmall",
    ] as const) {
      if (!isNonEmptyString(theme[field])) {
        addError("invalid-theme", `theme.${field}`, "A required theme value is missing.");
      }
    }

    for (const mode of ["light", "dark"] as const) {
      const palette = requireObject(theme[mode], `theme.${mode}`);
      if (palette) {
        themeTokenKeys.forEach((token) => {
          if (!isNonEmptyString(palette[token])) {
            addError(
              "invalid-theme",
              `theme.${mode}.${token}`,
              "A required theme token is missing.",
            );
          }
        });
      }
    }

    const overlay = requireObject(theme.heroOverlay, "theme.heroOverlay");
    if (overlay) {
      for (const mode of ["light", "dark"] as const) {
        if (!isNonEmptyString(overlay[mode])) {
          addError(
            "invalid-theme",
            `theme.heroOverlay.${mode}`,
            "A required hero overlay value is missing.",
          );
        }
      }
    }
  }

  const hero = requireObject(config.hero, "hero");
  if (hero) {
    requireString(hero.id, "hero.id");
    requireString(hero.kicker, "hero.kicker");
    requireString(hero.summary, "hero.summary");
    validateMedia(hero.art, "hero.art");

    const titleLines = hero.titleLines;
    if (
      !Array.isArray(titleLines) ||
      titleLines.length < 1 ||
      titleLines.length > 2 ||
      titleLines.some((line) => !isNonEmptyString(line))
    ) {
      addError(
        "invalid-title-lines",
        "hero.titleLines",
        "Hero title must contain one or two non-empty lines.",
      );
    }

    validateActionGroup(hero.actions, "hero.actions");

    if (!Array.isArray(hero.metrics)) {
      addError("invalid-config", "hero.metrics", "Hero metrics must be an array.");
    } else {
      if (hero.metrics.length > 4) {
        addError(
          "too-many-metrics",
          "hero.metrics",
          "Hero metrics can contain at most four items.",
        );
      }
      hero.metrics.forEach((metric, index) => {
        if (!isRecord(metric)) {
          addError(
            "invalid-config",
            `hero.metrics[${index}]`,
            "Metric items must be configuration objects.",
          );
          return;
        }
        for (const field of ["value", "label", "note"] as const) {
          requireString(metric[field], `hero.metrics[${index}].${field}`);
        }
      });
    }
  }

  const assistant = requireObject(config.assistant, "assistant");
  const knowledgeIds = new Set<string>();
  if (assistant) {
    for (const field of [
      "title",
      "status",
      "subtitle",
      "launcherAriaLabel",
      "launcherKicker",
      "launcherLabel",
      "disclaimer",
    ] as const) {
      requireString(assistant[field], `assistant.${field}`);
    }

    const initialMessage = requireObject(
      assistant.initialMessage,
      "assistant.initialMessage",
    );
    if (initialMessage) {
      requireString(initialMessage.text, "assistant.initialMessage.text");
      requireString(initialMessage.source, "assistant.initialMessage.source");
    }

    const labels = requireObject(assistant.labels, "assistant.labels");
    if (labels) {
      assistantLabelKeys.forEach((label) =>
        requireString(labels[label], `assistant.labels.${label}`),
      );
    }

    const fallback = requireObject(assistant.fallback, "assistant.fallback");
    if (fallback) {
      requireString(fallback.answer, "assistant.fallback.answer");
      requireString(fallback.source, "assistant.fallback.source");
    }

    if (!Array.isArray(assistant.knowledgeBase) || assistant.knowledgeBase.length < 1) {
      addError(
        "invalid-item-count",
        "assistant.knowledgeBase",
        "The knowledge base must contain at least one entry.",
      );
    } else {
      assistant.knowledgeBase.forEach((item, index) => {
        const path = `assistant.knowledgeBase[${index}]`;
        if (!isRecord(item)) {
          addError("invalid-config", path, "Knowledge entries must be objects.");
          return;
        }

        const id = item.id;
        if (!isNonEmptyString(id)) {
          addError(
            "invalid-knowledge-id",
            `${path}.id`,
            "Knowledge entries require a non-empty ID.",
          );
        } else if (knowledgeIds.has(id)) {
          addError(
            "duplicate-knowledge-id",
            `${path}.id`,
            "Knowledge entry IDs must be unique.",
          );
        } else {
          knowledgeIds.add(id);
        }

        for (const field of [
          "question",
          "shortQuestion",
          "answer",
          "source",
        ] as const) {
          requireString(item[field], `${path}.${field}`);
        }
        validateStringArray(item.keywords, `${path}.keywords`, 1, 20);
      });
    }

    if (!Array.isArray(assistant.quickQuestionIds)) {
      addError(
        "invalid-config",
        "assistant.quickQuestionIds",
        "Quick question IDs must be an array.",
      );
    } else {
      assistant.quickQuestionIds.forEach((id, index) => {
        if (!isNonEmptyString(id) || !knowledgeIds.has(id)) {
          addError(
            "invalid-knowledge-reference",
            `assistant.quickQuestionIds[${index}]`,
            "Quick questions must reference an existing knowledge ID.",
          );
        }
      });
    }
  }

  const sections = Array.isArray(config.sections) ? config.sections : [];
  if (!Array.isArray(config.sections)) {
    addError("invalid-config", "sections", "Sections must be an array.");
  } else if (sections.length < 1 || sections.length > 12) {
    addError(
      "invalid-item-count",
      "sections",
      "Sections must contain between one and twelve blocks.",
    );
  }

  const sectionIds = new Set<string>();
  let navCount = 0;

  sections.forEach((value, index) => {
    const path = `sections[${index}]`;
    if (!isRecord(value)) {
      addError("invalid-config", path, "Section blocks must be objects.");
      return;
    }

    if (!isNonEmptyString(value.id)) {
      addError(
        "invalid-section-id",
        `${path}.id`,
        "Section blocks require a non-empty ID.",
      );
    } else if (sectionIds.has(value.id)) {
      addError(
        "duplicate-section-id",
        `${path}.id`,
        "Section IDs must be unique.",
      );
    } else {
      sectionIds.add(value.id);
    }

    requireString(value.navLabel, `${path}.navLabel`);
    requireString(value.heading, `${path}.heading`);
    if (typeof value.showInNav !== "boolean") {
      addError(
        "invalid-required-field",
        `${path}.showInNav`,
        "Section navigation visibility must be a boolean.",
      );
    } else if (value.showInNav) {
      navCount += 1;
    }
    if (typeof value.description !== "string") {
      addError(
        "invalid-required-field",
        `${path}.description`,
        "Section description must be a string.",
      );
    }
    if (value.eyebrow !== undefined && !isNonEmptyString(value.eyebrow)) {
      addError(
        "invalid-required-field",
        `${path}.eyebrow`,
        "Section eyebrow must be non-empty when provided.",
      );
    }

    if (!isNonEmptyString(value.type) || !knownSectionTypes.has(value.type)) {
      addError(
        "invalid-section-type",
        `${path}.type`,
        "Section type is not supported.",
      );
      return;
    }

    switch (value.type) {
      case "feature-grid":
        validateItemObjects(
          value.businesses,
          `${path}.businesses`,
          ["icon", "eyebrow", "title", "description", "status"],
        );
        if (Array.isArray(value.businesses)) {
          value.businesses.forEach((business, businessIndex) => {
            validateStringArray(
              isRecord(business) ? business.points : undefined,
              `${path}.businesses[${businessIndex}].points`,
            );
          });
        }
        break;
      case "media-showcase":
        validateItemObjects(
          value.capabilities,
          `${path}.capabilities`,
          ["icon", "title", "description"],
        );
        requireString(value.visualLabel, `${path}.visualLabel`);
        requireString(value.visualTitle, `${path}.visualTitle`);
        validateMedia(value.visual, `${path}.visual`);
        validateAction(value.action, `${path}.action`);
        break;
      case "process":
        validateItemObjects(value.steps, `${path}.steps`, ["title", "text"]);
        if (Array.isArray(value.steps)) {
          value.steps.forEach((step, stepIndex) => {
            if (
              isRecord(step) &&
              step.path !== undefined &&
              !new Set(["shared", "branch-a", "branch-b"]).has(String(step.path))
            ) {
              addError(
                "invalid-config",
                `${path}.steps[${stepIndex}].path`,
                "Process step path must be shared, branch-a, or branch-b.",
              );
            }
          });
        }
        requireString(value.audienceHeading, `${path}.audienceHeading`);
        validateItemObjects(
          value.audiences,
          `${path}.audiences`,
          ["icon", "title", "description"],
        );
        break;
      case "evidence":
        validateMedia(value.visual, `${path}.visual`);
        for (const field of [
          "headlineMetric",
          "metricDescription",
          "themesAriaLabel",
          "caveat",
          "supportHeading",
          "supportNote",
        ] as const) {
          requireString(value[field], `${path}.${field}`);
        }
        validateStringArray(value.themes, `${path}.themes`);
        validateStringArray(value.supportNames, `${path}.supportNames`);
        break;
      case "engagement": {
        validateItemObjects(value.steps, `${path}.steps`, ["title", "text"]);
        const cta = requireObject(value.cta, `${path}.cta`);
        if (cta) {
          requireString(cta.title, `${path}.cta.title`);
          requireString(cta.description, `${path}.cta.description`);
          validateAction(cta.action, `${path}.cta.action`);
        }
        break;
      }
      case "faq":
        validateStringArray(value.itemIds, `${path}.itemIds`, 1, 30);
        if (Array.isArray(value.itemIds)) {
          value.itemIds.forEach((itemId, itemIndex) => {
            if (!isNonEmptyString(itemId) || !knowledgeIds.has(itemId)) {
              addError(
                "invalid-faq-reference",
                `${path}.itemIds[${itemIndex}]`,
                "FAQ entries must reference an existing knowledge ID.",
              );
            }
          });
        }
        if (value.action !== undefined) {
          validateAction(value.action, `${path}.action`);
        }
        break;
      case "closing":
        validateMedia(value.art, `${path}.art`);
        validateActionGroup(value.actions, `${path}.actions`);
        break;
    }
  });

  if (navCount > 6) {
    addError(
      "too-many-nav-items",
      "sections",
      "Navigation can contain at most six section links.",
    );
  }

  const footer = requireObject(config.footer, "footer");
  if (footer) {
    requireString(footer.brandNote, "footer.brandNote");
    requireString(footer.disclaimer, "footer.disclaimer");
    validateAction(footer.backToTopAction, "footer.backToTopAction");
  }

  return { valid: errors.length === 0, errors };
}
