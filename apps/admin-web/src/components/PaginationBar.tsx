import { Button } from "@fluentui/react-components";
import {
  ChevronLeft24Regular,
  ChevronRight24Regular,
} from "@fluentui/react-icons";

type PaginationBarProps = {
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
};

export function PaginationBar({
  total,
  limit,
  offset,
  onOffsetChange,
}: PaginationBarProps) {
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);
  return (
    <div className="pagination-bar" aria-label="分页">
      <span>
        第 {start}-{end} 条，共 {total} 条
      </span>
      <div>
        <Button
          appearance="subtle"
          size="small"
          icon={<ChevronLeft24Regular />}
          disabled={offset <= 0}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
        >
          上一页
        </Button>
        <Button
          appearance="subtle"
          size="small"
          iconPosition="after"
          icon={<ChevronRight24Regular />}
          disabled={offset + limit >= total}
          onClick={() => onOffsetChange(offset + limit)}
        >
          下一页
        </Button>
      </div>
    </div>
  );
}
