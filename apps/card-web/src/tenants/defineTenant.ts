import type { EnterpriseCardConfig } from "../domain/card";

export function defineTenant<const T extends EnterpriseCardConfig>(tenant: T): T {
  return tenant;
}
