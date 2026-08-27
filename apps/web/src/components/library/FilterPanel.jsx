import React, { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import Drawer from '../ui/Drawer';
import { LANE_ORDER, laneLabel } from '../../utils/corpusLanes';
import {
    ADDED_PRESETS,
    HEALTH_LABELS,
    KIND_LABELS,
    PAGE_PRESETS,
    REVIEW_LABELS,
    pagePresetFor,
    tagLabel,
} from '../../utils/libraryQuery';

const SEARCH_WITHIN_THRESHOLD = 8;

function Section({ title, activeCount = 0, defaultOpen = false, children }) {
    const [open, setOpen] = useState(defaultOpen || activeCount > 0);
    return (
        <section className={`fp-section ${open ? 'is-open' : ''}`}>
            <button
                type="button"
                className="fp-section-head"
                onClick={() => setOpen((value) => !value)}
                aria-expanded={open}
            >
                <span>{title}</span>
                {activeCount > 0 && <span className="fp-section-count">{activeCount}</span>}
            </button>
            {open && <div className="fp-section-body">{children}</div>}
        </section>
    );
}

function SearchWithin({ value, onChange, placeholder }) {
    return (
        <label className="fp-search">
            <Search size={13} aria-hidden="true" />
            <input
                type="search"
                value={value}
                onChange={(event) => onChange(event.target.value)}
                placeholder={placeholder}
                autoComplete="off"
            />
        </label>
    );
}

function CheckList({ options, selected, onToggle }) {
    if (!options.length) {
        return <p className="fp-empty">No values in the current result set.</p>;
    }
    return (
        <div className="fp-checklist" role="group">
            {options.map(({ value, label, count }) => (
                <label key={value} className={`fp-check ${selected.includes(value) ? 'is-checked' : ''}`}>
                    <input
                        type="checkbox"
                        checked={selected.includes(value)}
                        onChange={() => onToggle(value)}
                    />
                    <span className="fp-check-label">{label}</span>
                    {count != null && <span className="fp-check-count">{count}</span>}
                </label>
            ))}
        </div>
    );
}

function toggleValue(list, value) {
    return list.includes(value) ? list.filter((entry) => entry !== value) : [...list, value];
}

/** Options present in the facet counts plus any currently selected values that
 * filtering has counted to zero — selected rows must never vanish under you. */
function withSelected(counts, selected, labels, order = null) {
    const keys = new Set([...Object.keys(counts || {}), ...selected]);
    let values = [...keys];
    if (order) {
        values.sort((a, b) => order.indexOf(a) - order.indexOf(b));
    } else {
        values.sort((a, b) => (counts[b] || 0) - (counts[a] || 0));
    }
    return values.map((value) => ({
        value,
        label: labels?.[value] || value,
        count: counts?.[value] || 0,
    }));
}

function matchesWithin(options, needle) {
    const query = needle.trim().toLowerCase();
    if (!query) return options;
    return options.filter((option) => option.label.toLowerCase().includes(query));
}

/**
 * Instant-apply filter drawer. Every change commits to the URL immediately and the
 * list + counts re-query; the footer always says how many documents the current
 * selection produces.
 */
export default function FilterPanel({
    open,
    onClose,
    facets,
    facetCounts,
    onChangeFacets,
    onClearAll,
    filteredTotal,
}) {
    const [laneQuery, setLaneQuery] = useState('');
    const [yearQuery, setYearQuery] = useState('');
    const [tagQuery, setTagQuery] = useState('');

    const counts = facetCounts || {};
    const laneOptions = useMemo(
        () => withSelected(counts.lanes, facets.lanes, null, LANE_ORDER)
            .map((option) => ({ ...option, label: laneLabel(option.value) })),
        [counts.lanes, facets.lanes],
    );
    const kindOptions = useMemo(
        () => withSelected(counts.kinds, facets.kinds, KIND_LABELS,
            ['native-digital', 'scanned-ocr', 'mixed-ocr', 'unknown']),
        [counts.kinds, facets.kinds],
    );
    const reviewOptions = useMemo(
        () => withSelected(counts.review, facets.review, REVIEW_LABELS,
            ['complete', 'in_progress', 'untouched']),
        [counts.review, facets.review],
    );
    const healthOptions = useMemo(
        () => withSelected(counts.health, facets.health, HEALTH_LABELS,
            ['within_gate', 'outside_gate', 'unmeasured']),
        [counts.health, facets.health],
    );
    const yearOptions = useMemo(() => {
        const fromCounts = (counts.years || []).map(({ year, count }) => ({
            value: year, label: String(year), count,
        }));
        const missing = facets.years
            .filter((year) => !fromCounts.some((option) => option.value === year))
            .map((year) => ({ value: year, label: String(year), count: 0 }));
        return [...missing, ...fromCounts];
    }, [counts.years, facets.years]);
    const tagOptions = useMemo(() => {
        const fromCounts = (counts.tags || []).map(({ tag, count }) => ({
            value: tag, label: tagLabel(tag), count,
        }));
        const missing = facets.tags
            .filter((tag) => !fromCounts.some((option) => option.value === tag))
            .map((tag) => ({ value: tag, label: tagLabel(tag), count: 0 }));
        return [...missing, ...fromCounts];
    }, [counts.tags, facets.tags]);

    const update = (patch) => onChangeFacets({ ...facets, ...patch });
    const activePagesPreset = pagePresetFor(facets.pagesMin, facets.pagesMax);

    return (
        <Drawer
            open={open}
            onClose={onClose}
            title="Filter documents"
            width={400}
            className="library-filter-panel"
            headerExtra={(
                <span className="fp-result-count" aria-live="polite">
                    {filteredTotal.toLocaleString()} match{filteredTotal === 1 ? '' : 'es'}
                </span>
            )}
        >
            <Section title="Source" activeCount={facets.lanes.length} defaultOpen>
                {laneOptions.length > SEARCH_WITHIN_THRESHOLD && (
                    <SearchWithin value={laneQuery} onChange={setLaneQuery} placeholder="Search sources…" />
                )}
                <CheckList
                    options={matchesWithin(laneOptions, laneQuery)}
                    selected={facets.lanes}
                    onToggle={(lane) => update({ lanes: toggleValue(facets.lanes, lane) })}
                />
            </Section>

            <Section title="Format" activeCount={facets.kinds.length} defaultOpen>
                <CheckList
                    options={kindOptions}
                    selected={facets.kinds}
                    onToggle={(kind) => update({ kinds: toggleValue(facets.kinds, kind) })}
                />
            </Section>

            <Section title="Review status" activeCount={facets.review.length} defaultOpen>
                <CheckList
                    options={reviewOptions}
                    selected={facets.review}
                    onToggle={(value) => update({ review: toggleValue(facets.review, value) })}
                />
            </Section>

            <Section title="Health gate" activeCount={facets.health.length}>
                <CheckList
                    options={healthOptions}
                    selected={facets.health}
                    onToggle={(value) => update({ health: toggleValue(facets.health, value) })}
                />
            </Section>

            <Section
                title="Flags"
                activeCount={(facets.flagged ? 1 : 0) + (facets.annotations ? 1 : 0)}
            >
                <div className="fp-checklist" role="group">
                    <label className={`fp-check ${facets.flagged ? 'is-checked' : ''}`}>
                        <input
                            type="checkbox"
                            checked={facets.flagged}
                            onChange={() => update({ flagged: !facets.flagged })}
                        />
                        <span className="fp-check-label">Has flagged sections</span>
                    </label>
                    <label className={`fp-check ${facets.annotations ? 'is-checked' : ''}`}>
                        <input
                            type="checkbox"
                            checked={facets.annotations}
                            onChange={() => update({ annotations: !facets.annotations })}
                        />
                        <span className="fp-check-label">Has open annotations</span>
                    </label>
                </div>
            </Section>

            <Section title="Edition year" activeCount={facets.years.length || (facets.yearFrom != null || facets.yearTo != null ? 1 : 0)}>
                {yearOptions.length > SEARCH_WITHIN_THRESHOLD && (
                    <SearchWithin value={yearQuery} onChange={setYearQuery} placeholder="Search years…" />
                )}
                <CheckList
                    options={matchesWithin(yearOptions, yearQuery)}
                    selected={facets.years}
                    onToggle={(year) => update({ years: toggleValue(facets.years, year) })}
                />
                <div className="fp-range">
                    <span className="fp-range-label">Range</span>
                    <input
                        type="number"
                        min="1800"
                        max="2200"
                        placeholder="From"
                        value={facets.yearFrom ?? ''}
                        onChange={(event) => update({
                            yearFrom: event.target.value === '' ? null : Number(event.target.value),
                        })}
                        aria-label="Edition year from"
                    />
                    <span aria-hidden="true">–</span>
                    <input
                        type="number"
                        min="1800"
                        max="2200"
                        placeholder="To"
                        value={facets.yearTo ?? ''}
                        onChange={(event) => update({
                            yearTo: event.target.value === '' ? null : Number(event.target.value),
                        })}
                        aria-label="Edition year to"
                    />
                </div>
            </Section>

            <Section
                title="Date added"
                activeCount={facets.addedPreset || facets.addedAfter || facets.addedBefore ? 1 : 0}
            >
                <div className="fp-checklist" role="radiogroup" aria-label="Date added presets">
                    {[{ value: '', label: 'Any time' }, ...ADDED_PRESETS].map((preset) => (
                        <label key={preset.value || 'any'} className={`fp-check ${facets.addedPreset === preset.value ? 'is-checked' : ''}`}>
                            <input
                                type="radio"
                                name="fp-added"
                                checked={facets.addedPreset === preset.value}
                                onChange={() => update({
                                    addedPreset: preset.value, addedAfter: '', addedBefore: '',
                                })}
                            />
                            <span className="fp-check-label">{preset.label}</span>
                        </label>
                    ))}
                </div>
                <div className="fp-range">
                    <span className="fp-range-label">Custom</span>
                    <input
                        type="date"
                        value={facets.addedAfter}
                        onChange={(event) => update({ addedPreset: '', addedAfter: event.target.value })}
                        aria-label="Added after"
                    />
                    <span aria-hidden="true">–</span>
                    <input
                        type="date"
                        value={facets.addedBefore}
                        onChange={(event) => update({ addedPreset: '', addedBefore: event.target.value })}
                        aria-label="Added before"
                    />
                </div>
            </Section>

            <Section
                title="Pages"
                activeCount={facets.pagesMin != null || facets.pagesMax != null ? 1 : 0}
            >
                <div className="fp-checklist" role="radiogroup" aria-label="Page count presets">
                    {[{ value: '', label: 'Any size', min: null, max: null }, ...PAGE_PRESETS].map((preset) => (
                        <label key={preset.value || 'any'} className={`fp-check ${activePagesPreset === preset.value ? 'is-checked' : ''}`}>
                            <input
                                type="radio"
                                name="fp-pages"
                                checked={activePagesPreset === preset.value}
                                onChange={() => update({ pagesMin: preset.min, pagesMax: preset.max })}
                            />
                            <span className="fp-check-label">{preset.label}</span>
                        </label>
                    ))}
                </div>
                <div className="fp-range">
                    <span className="fp-range-label">Custom</span>
                    <input
                        type="number"
                        min="0"
                        placeholder="Min"
                        value={facets.pagesMin ?? ''}
                        onChange={(event) => update({
                            pagesMin: event.target.value === '' ? null : Number(event.target.value),
                        })}
                        aria-label="Minimum pages"
                    />
                    <span aria-hidden="true">–</span>
                    <input
                        type="number"
                        min="0"
                        placeholder="Max"
                        value={facets.pagesMax ?? ''}
                        onChange={(event) => update({
                            pagesMax: event.target.value === '' ? null : Number(event.target.value),
                        })}
                        aria-label="Maximum pages"
                    />
                </div>
            </Section>

            {tagOptions.length > 0 && (
                <Section title="Tags" activeCount={facets.tags.length}>
                    {tagOptions.length > SEARCH_WITHIN_THRESHOLD && (
                        <SearchWithin value={tagQuery} onChange={setTagQuery} placeholder="Search tags…" />
                    )}
                    <CheckList
                        options={matchesWithin(tagOptions, tagQuery)}
                        selected={facets.tags}
                        onToggle={(tag) => update({ tags: toggleValue(facets.tags, tag) })}
                    />
                </Section>
            )}

            <div className="fp-footer">
                <button type="button" className="btn btn-sm btn-secondary" onClick={onClearAll}>
                    Clear all filters
                </button>
                <button type="button" className="btn btn-sm btn-primary" onClick={onClose}>
                    Show {filteredTotal.toLocaleString()} document{filteredTotal === 1 ? '' : 's'}
                </button>
            </div>
        </Drawer>
    );
}
