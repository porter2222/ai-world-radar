from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha1

from sqlalchemy import select
from sqlalchemy.orm import Session

from worker.models import Source, SourceSignal


@dataclass
class EditorialCandidateGroup:
    """selector 前的候选事件分组。

    输入：一个或多个通过硬过滤的 SourceSignal。
    输出：供 LLM Editorial Selector 消费的轻量分组对象，不直接写库或发布。
    """

    group_id: str
    group_key: str
    title: str
    signal_ids: list[str] = field(default_factory=list)
    source_keys: list[str] = field(default_factory=list)
    canonical_url: str | None = None
    repo_full_name: str | None = None
    merge_reason: str = "single_signal"


class EditorialCandidateService:
    """编辑筛选候选准备服务。

    输入：SQLAlchemy Session。
    输出：从 source_signals 读取、硬过滤并聚合出的 EditorialCandidateGroup 列表。
    """

    def __init__(self, session: Session):
        """初始化服务。

        输入：外部传入且由调用方管理事务的 Session。
        输出：可复用的 EditorialCandidateService 实例。
        """
        self.session = session

    def build_candidate_groups(
        self,
        *,
        lookback_hours: int = 48,
        candidate_pool_limit: int = 60,
        exclude_processed: bool = True,
        now: datetime | None = None,
    ) -> list[EditorialCandidateGroup]:
        """构造 selector 候选分组。

        输入：时间窗口、候选池上限、是否排除已处理信号和可选当前时间。
        输出：经过硬过滤和分组合并后的 EditorialCandidateGroup 列表。
        """
        signal_rows = self._load_signals(limit=candidate_pool_limit)
        return self.build_candidate_groups_from_rows(
            signal_rows,
            lookback_hours=lookback_hours,
            exclude_processed=exclude_processed,
            now=now,
        )

    def build_candidate_groups_from_rows(
        self,
        signal_rows: list[tuple[SourceSignal, str]],
        *,
        lookback_hours: int = 48,
        exclude_processed: bool = True,
        now: datetime | None = None,
    ) -> list[EditorialCandidateGroup]:
        """从调用方显式传入的信号行构造 selector 候选分组。

        输入：`(SourceSignal, source_key)` 行列表、时间窗口、是否排除已处理信号和当前时间。
        输出：复用同一套硬过滤与合并规则得到的 EditorialCandidateGroup 列表。
        """
        return self._build_candidate_groups_from_rows(
            signal_rows,
            lookback_hours=lookback_hours,
            exclude_processed=exclude_processed,
            now=now,
        )

    def _load_signals(self, *, limit: int) -> list[tuple[SourceSignal, str]]:
        """读取候选池内来源信号。

        输入：候选池最大行数。
        输出：按采集时间正序排列的 `(SourceSignal, source_key)` 列表。
        """
        rows = self.session.execute(
            select(SourceSignal, Source.source_key)
            .join(Source, Source.id == SourceSignal.source_id)
            .order_by(SourceSignal.collected_at.asc(), SourceSignal.id.asc())
            .limit(limit)
        ).all()
        return [(row[0], row[1]) for row in rows]

    def _build_candidate_groups_from_rows(
        self,
        signal_rows: list[tuple[SourceSignal, str]],
        *,
        lookback_hours: int,
        exclude_processed: bool,
        now: datetime | None,
    ) -> list[EditorialCandidateGroup]:
        """把来源信号行转换为候选分组。

        输入：已排序的 `(SourceSignal, source_key)` 行列表、窗口和过滤开关。
        输出：经过硬过滤、URL/repo/标题合并后的候选 group 列表。
        """
        groups: list[EditorialCandidateGroup] = []
        url_index: dict[str, EditorialCandidateGroup] = {}
        repo_index: dict[str, EditorialCandidateGroup] = {}
        seen_source_hashes: set[str] = set()
        cutoff = self._build_cutoff(lookback_hours=lookback_hours, now=now)

        for signal, source_key in signal_rows:
            if not self._is_eligible_signal(
                signal,
                cutoff=cutoff,
                exclude_processed=exclude_processed,
                seen_source_hashes=seen_source_hashes,
            ):
                continue

            canonical_url = normalize_url(signal.canonical_url or signal.original_url)
            repo_full_name = extract_repo_full_name(signal)
            group, merge_reason = self._find_existing_group(
                signal,
                groups=groups,
                url_index=url_index,
                repo_index=repo_index,
                canonical_url=canonical_url,
                repo_full_name=repo_full_name,
            )
            if group is None:
                group = self._new_group(signal, canonical_url=canonical_url, repo_full_name=repo_full_name)
                groups.append(group)
            else:
                group.merge_reason = merge_reason

            self._append_signal(group, signal=signal, source_key=source_key)
            if canonical_url:
                url_index[canonical_url] = group
            if repo_full_name:
                repo_index[repo_full_name] = group

        return groups

    def _is_eligible_signal(
        self,
        signal: SourceSignal,
        *,
        cutoff: datetime,
        exclude_processed: bool,
        seen_source_hashes: set[str],
    ) -> bool:
        """判断单条信号是否能进入 selector 候选池。

        输入：SourceSignal、时间窗口 cutoff、是否排除已处理信号和本轮已见 source_hash 集合。
        输出：符合硬过滤规则返回 True，否则返回 False。
        """
        if not (signal.original_title or "").strip():
            return False
        if not (signal.canonical_url or signal.original_url):
            return False
        if exclude_processed and signal.pipeline_run_id:
            return False
        if signal.source_hash in seen_source_hashes:
            return False

        event_time = normalize_datetime(signal.published_at or signal.collected_at)
        if event_time and event_time < cutoff:
            return False

        seen_source_hashes.add(signal.source_hash)
        return True

    def _find_existing_group(
        self,
        signal: SourceSignal,
        *,
        groups: list[EditorialCandidateGroup],
        url_index: dict[str, EditorialCandidateGroup],
        repo_index: dict[str, EditorialCandidateGroup],
        canonical_url: str | None,
        repo_full_name: str | None,
    ) -> tuple[EditorialCandidateGroup | None, str]:
        """为信号查找可合并的已有 group。

        输入：当前信号、已有 group、URL 索引、repo 索引、规范 URL 和 repo 名。
        输出：匹配到的 group 及合并原因；没有匹配时返回 `(None, "single_signal")`。
        """
        if canonical_url and canonical_url in url_index:
            return url_index[canonical_url], "same_canonical_url"
        if repo_full_name and repo_full_name in repo_index:
            return repo_index[repo_full_name], "same_repo"
        for group in groups:
            if title_similarity(signal.original_title, group.title) >= 0.6:
                return group, "similar_title"
        return None, "single_signal"

    def _new_group(
        self,
        signal: SourceSignal,
        *,
        canonical_url: str | None,
        repo_full_name: str | None,
    ) -> EditorialCandidateGroup:
        """创建新的候选事件 group。

        输入：首条 SourceSignal、可选规范 URL 和 repo 名。
        输出：尚未追加 signal_ids 的 EditorialCandidateGroup。
        """
        group_key = build_group_key(signal, canonical_url=canonical_url, repo_full_name=repo_full_name)
        return EditorialCandidateGroup(
            group_id=f"group_{sha1(group_key.encode('utf-8')).hexdigest()[:12]}",
            group_key=group_key,
            title=signal.original_title.strip(),
            canonical_url=canonical_url,
            repo_full_name=repo_full_name,
        )

    def _append_signal(self, group: EditorialCandidateGroup, *, signal: SourceSignal, source_key: str) -> None:
        """把信号追加到候选 group。

        输入：目标 group、SourceSignal 和 source_key。
        输出：无返回值；原地更新 signal_ids 与 source_keys。
        """
        if signal.id not in group.signal_ids:
            group.signal_ids.append(signal.id)
        if source_key not in group.source_keys:
            group.source_keys.append(source_key)

    def _build_cutoff(self, *, lookback_hours: int, now: datetime | None) -> datetime:
        """构造时间窗口 cutoff。

        输入：窗口小时数和可选当前时间。
        输出：带 UTC 时区的 cutoff datetime。
        """
        current = normalize_datetime(now or datetime.now(UTC)) or datetime.now(UTC)
        return current - timedelta(hours=lookback_hours)


def build_group_key(signal: SourceSignal, *, canonical_url: str | None, repo_full_name: str | None) -> str:
    """生成候选 group 的稳定 key。

    输入：SourceSignal、可选 canonical_url 和 repo_full_name。
    输出：优先按 URL，其次按 repo，最后按标题 token 构造的 group key。
    """
    if canonical_url:
        return f"url:{canonical_url}"
    if repo_full_name:
        return f"repo:{repo_full_name}"
    return f"title:{'-'.join(sorted(title_tokens(signal.original_title)))}"


def normalize_url(value: str | None) -> str | None:
    """规范化 URL 用于分组。

    输入：原始 URL 或 canonical URL。
    输出：去掉首尾空格和末尾斜杠后的小写 URL；空值返回 None。
    """
    if not value:
        return None
    normalized = value.strip().rstrip("/").lower()
    return normalized or None


def normalize_datetime(value: datetime | None) -> datetime | None:
    """统一 datetime 时区。

    输入：可选 datetime，可能为 naive 或 aware。
    输出：aware UTC datetime；空值返回 None。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def extract_repo_full_name(signal: SourceSignal) -> str | None:
    """从信号 metadata、source_item_id 或 GitHub URL 中提取 repo 名。

    输入：SourceSignal。
    输出：`owner/repo` 小写形式；无法识别时返回 None。
    """
    metadata = signal.metadata_json or {}
    full_name = metadata.get("full_name")
    if isinstance(full_name, str) and "/" in full_name:
        return full_name.lower()

    owner = metadata.get("owner")
    repo = metadata.get("repo")
    if isinstance(owner, str) and isinstance(repo, str) and owner and repo:
        return f"{owner.lower()}/{repo.lower()}"

    source_item_id = signal.source_item_id or ""
    source_item_repo = source_item_id.split("#", maxsplit=1)[0]
    if re.fullmatch(r"[\w.-]+/[\w.-]+", source_item_repo):
        return source_item_repo.lower()

    url = signal.canonical_url or signal.original_url or ""
    match = re.search(r"github\.com/([\w.-]+/[\w.-]+)", url, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


def title_similarity(first: str, second: str) -> float:
    """计算两个标题的 token 相似度。

    输入：两个标题字符串。
    输出：0 到 1 之间的 Jaccard 相似度。
    """
    first_tokens = title_tokens(first)
    second_tokens = title_tokens(second)
    if not first_tokens or not second_tokens:
        return 0.0
    return len(first_tokens & second_tokens) / len(first_tokens | second_tokens)


def title_tokens(value: str) -> set[str]:
    """提取标题关键词 token。

    输入：标题字符串。
    输出：去掉常见停用词后的 token 集合，用于近似标题合并。
    """
    stop_words = {
        "a",
        "an",
        "and",
        "for",
        "in",
        "is",
        "new",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
    raw_tokens = re.sub(r"[^a-zA-Z0-9]+", " ", value.lower()).split()
    return {token for token in raw_tokens if token not in stop_words and len(token) >= 2}
