from app.core.config import settings
from app.models.schemas import Source


def deduplicate_sources(sources: list[Source]) -> list[Source]:
    groups: dict[tuple[str, int | None], list[Source]] = {}
    order: list[tuple[str, int | None]] = []
    for s in sources:
        key = (s.doc_id, s.page)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(s)

    merged: list[Source] = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            merged.append(group[0])
            continue

        texts = []
        min_start = None
        max_end = None
        best_relevance = None
        for s in group:
            texts.append(s.text)
            if s.start_char is not None:
                min_start = min(min_start, s.start_char) if min_start is not None else s.start_char
            if s.end_char is not None:
                max_end = max(max_end, s.end_char) if max_end is not None else s.end_char
            if s.relevance is not None:
                best_relevance = max(best_relevance, s.relevance) if best_relevance is not None else s.relevance

        combined = " … ".join(texts)[:settings.source_text_max_length]
        merged.append(Source(
            document=group[0].document,
            doc_id=group[0].doc_id,
            chunk_id=group[0].chunk_id,
            text=combined,
            page=group[0].page,
            page_end=group[0].page_end,
            start_char=min_start,
            end_char=max_end,
            relevance=best_relevance,
        ))
    return merged
