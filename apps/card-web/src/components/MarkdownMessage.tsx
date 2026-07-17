import type { ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function safeExternalHref(href: string | undefined): string | undefined {
  if (!href) return undefined;
  const normalized = href.trim();
  return /^(https?:\/\/|mailto:)/i.test(normalized) ? normalized : undefined;
}

function MarkdownLink({ href, children }: ComponentPropsWithoutRef<"a">) {
  const safeHref = safeExternalHref(href);
  if (!safeHref) return <>{children}</>;

  return (
    <a href={safeHref} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  );
}

export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="message-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: MarkdownLink }}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
