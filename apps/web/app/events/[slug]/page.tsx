import { notFound } from "next/navigation";

import { EventDetail } from "../../../components/EventDetail";
import { ProductApiError, getEventDetail } from "../../../lib/product-api";

type EventDetailPageProps = {
  params: Promise<{
    slug: string;
  }>;
};

export default async function EventDetailPage({ params }: EventDetailPageProps) {
  const { slug } = await params;

  try {
    const event = await getEventDetail(slug);
    return (
      <main className="shell" id="appMain">
        <section className="dossier-pane view is-active" aria-live="polite">
          <EventDetail event={event} />
        </section>
      </main>
    );
  } catch (error) {
    if (error instanceof ProductApiError && error.isNotFound) {
      notFound();
    }
    throw error;
  }
}
