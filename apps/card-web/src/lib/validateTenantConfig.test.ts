import { describe, expect, it } from "vitest";

import type {
  EnterpriseCardConfig,
  FeatureGridSection,
  FaqSection,
  ProcessSection,
} from "../domain/card";
import { templateTenant } from "../tenants/template/tenant";
import { tuotuTenant } from "../tenants/tuotu/tenant";
import { validateTenantConfig } from "./validateTenantConfig";

const cloneTenant = () =>
  structuredClone(tuotuTenant) as unknown as EnterpriseCardConfig;

const getFeatureGrid = (config: EnterpriseCardConfig) =>
  config.sections.find(
    (section): section is FeatureGridSection => section.type === "feature-grid",
  )!;

const getFaq = (config: EnterpriseCardConfig) =>
  config.sections.find((section): section is FaqSection => section.type === "faq")!;

const getProcess = (config: EnterpriseCardConfig) =>
  config.sections.find(
    (section): section is ProcessSection => section.type === "process",
  )!;

describe("validateTenantConfig", () => {
  it("accepts the curated Tuotu tenant", () => {
    expect(validateTenantConfig(tuotuTenant)).toEqual({ valid: true, errors: [] });
  });

  it("accepts the runnable generic template tenant", () => {
    expect(validateTenantConfig(templateTenant)).toEqual({ valid: true, errors: [] });
  });

  it("rejects a config that omits required runtime objects", () => {
    const config = cloneTenant() as unknown as Record<string, unknown>;
    delete config.brand;
    delete config.theme;
    delete config.assistant;
    delete config.footer;

    const result = validateTenantConfig(config);

    expect(result.valid).toBe(false);
    expect(result.errors).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "invalid-config", path: "brand" }),
        expect.objectContaining({ code: "invalid-config", path: "theme" }),
        expect.objectContaining({ code: "invalid-config", path: "assistant" }),
        expect.objectContaining({ code: "invalid-config", path: "footer" }),
      ]),
    );
  });

  it("requires the official action to be external", () => {
    const config = cloneTenant() as unknown as {
      brand: { officialAction: unknown };
    };
    config.brand.officialAction = {
      kind: "anchor",
      label: "站内入口",
      target: "#top",
    };

    const result = validateTenantConfig(config);

    expect(result.errors).toContainEqual(
      expect.objectContaining({
        code: "invalid-action-target",
        path: "brand.officialAction",
      }),
    );
  });

  it("requires media source and alternative text fields", () => {
    const config = cloneTenant() as unknown as {
      hero: { art: Record<string, unknown> };
    };
    delete config.hero.art.alt;

    const result = validateTenantConfig(config);

    expect(result.errors).toContainEqual(
      expect.objectContaining({ code: "invalid-media", path: "hero.art.alt" }),
    );
  });

  it("rejects duplicate section IDs without returning the duplicated content", () => {
    const config = cloneTenant();
    config.sections[1].id = config.sections[0].id;

    const result = validateTenantConfig(config);

    expect(result.valid).toBe(false);
    expect(result.errors).toContainEqual(
      expect.objectContaining({ code: "duplicate-section-id", path: "sections[1].id" }),
    );
    expect(JSON.stringify(result.errors)).not.toContain(config.sections[0].id);
  });

  it("rejects duplicate knowledge IDs", () => {
    const config = cloneTenant();
    config.assistant.knowledgeBase[1].id = config.assistant.knowledgeBase[0].id;

    const result = validateTenantConfig(config);

    expect(result.errors).toContainEqual(
      expect.objectContaining({ code: "duplicate-knowledge-id" }),
    );
  });

  it("rejects an FAQ reference outside the knowledge base", () => {
    const config = cloneTenant();
    getFaq(config).itemIds[0] = "missing-knowledge-entry";

    const result = validateTenantConfig(config);

    expect(result.errors).toContainEqual(
      expect.objectContaining({ code: "invalid-faq-reference" }),
    );
  });

  it("rejects more than two hero actions", () => {
    const config = cloneTenant();
    config.hero.actions.push({
      kind: "anchor",
      label: "第三个入口",
      target: "#faq",
    });

    const result = validateTenantConfig(config);

    expect(result.errors).toContainEqual(
      expect.objectContaining({ code: "too-many-actions", path: "hero.actions" }),
    );
  });

  it.each([2, 4, 6])("accepts a feature grid containing %i items", (count) => {
    const config = cloneTenant();
    const grid = getFeatureGrid(config);
    const source = grid.businesses[0];
    grid.businesses = Array.from({ length: count }, () => structuredClone(source));

    expect(validateTenantConfig(config).valid).toBe(true);
  });

  it("rejects an action target that does not match its kind", () => {
    const config = cloneTenant();
    config.hero.actions[0] = {
      kind: "external",
      label: "错误链接",
      target: "#not-an-external-url",
    };

    const result = validateTenantConfig(config);

    expect(result.errors).toContainEqual(
      expect.objectContaining({
        code: "invalid-action-target",
        path: "hero.actions[0]",
      }),
    );
  });

  it("rejects an unsupported process branch marker", () => {
    const config = cloneTenant();
    const step = getProcess(config).steps[0] as unknown as { path: string };
    step.path = "branch-c";

    const result = validateTenantConfig(config);

    expect(result.errors).toContainEqual(
      expect.objectContaining({
        code: "invalid-config",
        path: expect.stringContaining("steps[0].path"),
      }),
    );
  });
});
