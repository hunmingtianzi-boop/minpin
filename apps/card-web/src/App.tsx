import { useRef } from "react";

import "./styles.css";

import {
  DeferredAIAssistant,
  type AIAssistantHandle,
} from "./components/DeferredAIAssistant";
import {
  DeferredPublicExperience,
  type PublicExperienceHandle,
} from "./components/DeferredPublicExperience";
import type { EnterpriseCardConfig } from "./domain/card";
import type { PublicCardData } from "./lib/publicCardApi";
import { canonicalShareUrl } from "./lib/publicExperienceApi";
import { BusinessCardPrototypeApp } from "./prototype/BusinessCardPrototypeApp";

export default function App({
  tenant,
  publishedCard,
}: {
  tenant: EnterpriseCardConfig;
  publishedCard?: PublicCardData;
}) {
  const assistantRef = useRef<AIAssistantHandle>(null);
  const publicExperienceRef = useRef<PublicExperienceHandle>(null);
  const assistantEnabled = publishedCard?.ai_assistant.available ?? true;

  const openAssistant = (question?: string) => {
    if (question?.trim()) assistantRef.current?.openWithQuestion(question.trim());
    else assistantRef.current?.open();
  };

  const openLead = () => {
    if (publishedCard) publicExperienceRef.current?.openLead();
    else openAssistant("我想提交合作需求，请告诉我如何联系");
  };

  const shareFallback = async () => {
    const url = canonicalShareUrl(window.location);
    if (navigator.share) {
      await navigator.share({ title: tenant.seo.title, text: tenant.seo.description, url });
      return;
    }
    await navigator.clipboard.writeText(url);
  };

  const openShare = () => {
    if (publishedCard) publicExperienceRef.current?.openShare();
    else void shareFallback().catch(() => undefined);
  };

  return (
    <>
      <BusinessCardPrototypeApp
        tenant={tenant}
        card={publishedCard}
        onAssistant={openAssistant}
        onLead={openLead}
        onPrivacy={() => publicExperienceRef.current?.openPrivacy()}
        onProfile={() => publicExperienceRef.current?.openProfile()}
        onShare={openShare}
      />

      {publishedCard && (
        <DeferredPublicExperience
          ref={publicExperienceRef}
          card={publishedCard}
          controllerOnly
          onAssistant={openAssistant}
        />
      )}

      {assistantEnabled && (
        <DeferredAIAssistant
          key={tenant.id}
          ref={assistantRef}
          config={tenant.assistant}
          cardSlug={publishedCard?.slug ?? tenant.id}
          onLeadPrompt={publishedCard ? openLead : undefined}
        />
      )}
    </>
  );
}
