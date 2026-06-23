import Link from "next/link";

import { formatRelativeTime, sourceDomain, splitBodyParagraphs } from "../lib/format";
import type { ProductEventDetail } from "../lib/product-api";

type EventDetailProps = {
  event: ProductEventDetail;
  now?: Date;
};

export function EventDetail({ event, now }: EventDetailProps) {
  const category = event.category || "AI 事件";
  const paragraphs = splitBodyParagraphs(event.detail_body);
  const coverClassName = event.cover_image_url ? "cover detail-cover" : "cover detail-cover is-fallback";
  const updatedText = `最后更新 ${formatRelativeTime(event.published_at, now)}`;

  return (
    <article className="dossier">
      <Link className="back-link" href="/">
        ← 返回事件流
      </Link>

      <div className={coverClassName}>
        {event.cover_image_url ? (
          <img src={event.cover_image_url} alt={`${event.title} 封面图`} />
        ) : null}
        <div className="cover-fallback" data-testid="detail-cover-fallback">
          {category}
        </div>
      </div>

      <div className="detail-meta">
        <span className="pill">{category}</span>
        {event.signal_label ? <span className="pill signal">{event.signal_label}</span> : null}
        <span className="time">{formatRelativeTime(event.published_at, now)}</span>
      </div>

      <h2 className="detail-title">{event.title}</h2>
      <p className="detail-summary">{event.detail_summary}</p>

      <div className="article-body">
        {paragraphs.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
      </div>

      <section className="note-box" aria-labelledby="why-title">
        <h3 className="note-title" id="why-title">
          为什么值得看
        </h3>
        <p>{event.why_it_matters}</p>
      </section>

      {event.follow_up_points.length > 0 ? (
        <section className="note-box" aria-labelledby="follow-title">
          <h3 className="note-title" id="follow-title">
            继续观察
          </h3>
          <ul className="follow-list">
            {event.follow_up_points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {event.source_refs.length > 0 ? (
        <section className="note-box" aria-labelledby="source-title">
          <h3 className="note-title" id="source-title">
            来源
          </h3>
          <ul className="source-list">
            {event.source_refs.map((source, index) => {
              const href = source.url || "#";
              const label = source.title || sourceDomain(source.url) || "来源";
              return (
                <li key={`${href}-${index}`}>
                  <a href={href} target="_blank" rel="noreferrer">
                    <span className="source-name">{label}</span>
                    <span className="source-domain">{sourceDomain(source.url)}</span>
                  </a>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      <div className="detail-footer">{updatedText}</div>
    </article>
  );
}
