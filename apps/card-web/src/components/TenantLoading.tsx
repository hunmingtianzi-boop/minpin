import { Buildings } from "@phosphor-icons/react";

export function TenantLoading() {
  return (
    <main className="tenant-error" aria-busy="true" aria-live="polite">
      <div className="tenant-error-panel tenant-loading-panel">
        <span className="tenant-error-icon" aria-hidden="true">
          <Buildings size={30} weight="duotone" />
        </span>
        <p>创非凡数智名片</p>
        <h1>正在加载企业资料</h1>
        <p className="tenant-error-description">正在核对企业发布状态与公开内容。</p>
        <div className="tenant-loading-lines" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
      </div>
    </main>
  );
}
