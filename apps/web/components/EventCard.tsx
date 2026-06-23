import Link from "next/link";

import { formatRelativeTime } from "../lib/format";
import type { ProductEventListItem } from "../lib/product-api";

type EventCardProps = {
  event: ProductEventListItem;
  now?: Date;
};

export function EventCard({ event, now }: EventCardProps) {
  const category = event.category || "AI 事件";
  const sourceHint = event.source_hint || "来源待补";
  const coverClassName = event.cover_image_url ? "cover" : "cover is-fallback";

  return (
    <Link className="event-card" href={`/events/${event.slug}`}>
      <div className={coverClassName}>
        {event.cover_image_url ? (
          <img src={event.cover_image_url} alt={`${event.title} 封面图`} loading="lazy" />
        ) : null}
        <div className="cover-fallback" data-testid="cover-fallback">
          {category}
        </div>
      </div>

      <div className="card-body">
        <div className="meta-row">
          <span className="pill">{category}</span>
          {event.signal_label ? <span className="pill signal">{event.signal_label}</span> : null}
        </div>
        <h2 className="card-title">{event.title}</h2>
        <p className="card-summary">{event.card_summary}</p>
      </div>

      <div className="card-side" aria-label="来源和发布时间">
        <strong className="event-card__source">{sourceHint}</strong>
        <span className="time">{formatRelativeTime(event.published_at, now)}</span>
      </div>
    </Link>
  );
}
