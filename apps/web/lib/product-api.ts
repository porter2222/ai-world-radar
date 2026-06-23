export type ProductEventListItem = {
  id: string;
  slug: string;
  title: string;
  card_summary: string;
  detail_summary: string;
  category: string | null;
  signal_label: string | null;
  cover_image_url: string | null;
  homepage_rank: number | null;
  source_hint: string | null;
  source_count: number;
  published_at: string;
};

export type SourceRef = {
  title?: string;
  url?: string;
  source_key?: string;
  signal_id?: string;
};

export type ProductEventDetail = {
  id: string;
  slug: string;
  title: string;
  detail_summary: string;
  detail_body: string;
  why_it_matters: string;
  follow_up_points: string[];
  source_refs: SourceRef[];
  category: string | null;
  signal_label: string | null;
  cover_image_url: string | null;
  published_at: string;
};

export type ProductEventListResponse = {
  items: ProductEventListItem[];
  limit: number;
  offset: number;
};

type EventsQuery = {
  limit?: number;
  offset?: number;
  category?: string;
};

export class ProductApiError extends Error {
  readonly status: number;
  readonly isNotFound: boolean;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ProductApiError";
    this.status = status;
    this.isNotFound = status === 404;
  }
}

export async function getEvents(query: EventsQuery = {}): Promise<ProductEventListResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(query.limit ?? 20));
  params.set("offset", String(query.offset ?? 0));
  if (query.category) {
    params.set("category", query.category);
  }

  return fetchJson<ProductEventListResponse>(`/events?${params.toString()}`);
}

export async function getEventDetail(slug: string): Promise<ProductEventDetail> {
  return fetchJson<ProductEventDetail>(`/events/${encodeURIComponent(slug)}`);
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new ProductApiError(await errorMessage(response), response.status);
  }
  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : `Product API error ${response.status}`;
  } catch {
    return `Product API error ${response.status}`;
  }
}

function apiBaseUrl(): string {
  return (process.env.AI_WORLD_RADAR_API_BASE_URL || "http://127.0.0.1:8016").replace(/\/+$/, "");
}
