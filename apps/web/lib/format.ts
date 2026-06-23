export function formatRelativeTime(value: string, now = new Date()): string {
  const date = new Date(value);
  const diffMs = now.getTime() - date.getTime();
  const minuteMs = 60 * 1000;
  const hourMs = 60 * minuteMs;
  const dayMs = 24 * hourMs;

  if (Number.isNaN(date.getTime())) {
    return "";
  }

  if (diffMs < hourMs) {
    return `${Math.max(1, Math.floor(diffMs / minuteMs))} 分钟前`;
  }

  if (diffMs < dayMs) {
    return `${Math.floor(diffMs / hourMs)} 小时前`;
  }

  if (diffMs < 2 * dayMs) {
    return "昨天";
  }

  return `${date.getUTCFullYear()}.${pad(date.getUTCMonth() + 1)}.${pad(date.getUTCDate())}`;
}

export function splitBodyParagraphs(body: string): string[] {
  return body
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

export function sourceDomain(url: string | undefined): string {
  if (!url) {
    return "";
  }

  try {
    return new URL(url).hostname;
  } catch {
    return url.replace(/^https?:\/\//, "");
  }
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}
