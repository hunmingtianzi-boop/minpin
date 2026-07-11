import { Skeleton, SkeletonItem } from "@fluentui/react-components";

export function BootScreen() {
  return (
    <main className="boot-screen" role="status" aria-label="正在恢复登录状态">
      <div className="boot-card">
        <Skeleton>
          <SkeletonItem size={32} />
          <SkeletonItem size={16} />
          <SkeletonItem size={48} />
        </Skeleton>
      </div>
    </main>
  );
}
