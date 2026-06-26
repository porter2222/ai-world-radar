import { EventCard } from "../components/EventCard";
import { getEvents } from "../lib/product-api";

export default async function HomePage() {
  const events = await getEvents();

  return (
    <main className="shell" id="appMain">
      <section className="feed-pane view is-active" aria-labelledby="portalTitle">
        <section className="portal-hero" aria-labelledby="portalTitle">
          <h1 className="portal-title" id="portalTitle">
            全球 AI 事件雷达
          </h1>
          <p className="portal-index">Agent 工程 / SDK 演进 / 开源运行时</p>
        </section>

        <div className="event-list" aria-label="事件列表">
          {events.items.length > 0 ? (
            events.items.map((event) => <EventCard key={event.id} event={event} />)
          ) : (
            <div className="empty-state">暂无已发布事件</div>
          )}
        </div>
      </section>
    </main>
  );
}
