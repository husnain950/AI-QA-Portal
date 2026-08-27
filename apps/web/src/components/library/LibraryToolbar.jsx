import React from 'react';
import {
    ChevronDown, FolderTree, History, LayoutGrid, Library, List, Rows3, Search,
    SlidersHorizontal, Star, X,
} from 'lucide-react';
import DropdownMenu from '../ui/DropdownMenu';
import SegmentedControl from '../ui/SegmentedControl';
import SavedViewsMenu from './SavedViewsMenu';
import { SORT_GROUPS, sortLabel } from '../../utils/libraryQuery';

const VIEW_ICONS = {
    all: <Library size={13} aria-hidden="true" />,
    favorites: <Star size={13} aria-hidden="true" />,
    recent: <History size={13} aria-hidden="true" />,
};

function sortMenuItems(sort, searching, onSort) {
    const items = [];
    for (const [groupIndex, group] of SORT_GROUPS.entries()) {
        const options = group.options.filter((option) => !option.searchOnly || searching);
        if (!options.length) continue;
        if (items.length) items.push({ type: 'separator', key: `sep-${groupIndex}` });
        if (group.label) items.push({ type: 'header', label: group.label });
        for (const option of options) {
            items.push({
                key: option.value,
                label: option.label,
                active: option.value === sort,
                onSelect: () => onSort(option.value),
            });
        }
    }
    return items;
}

/**
 * The Library command bar: instant search, filters, sort, views, densities,
 * grouping, saved views — plus the active-filter chip row. Sticky via CSS.
 */
export default function LibraryToolbar({
    queryInput,
    onQueryInput,
    searching,
    sort,
    onSort,
    view,
    onView,
    viewCounts,
    layout,
    onLayout,
    group,
    onToggleGroup,
    filterCount,
    onOpenFilters,
    chips,
    onRemoveChip,
    onClearAll,
    total,
    libraryTotal,
    loading,
    currentSearch,
    onApplySavedView,
}) {
    const narrowed = total !== libraryTotal;
    return (
        <div className="library-toolbar">
            <div className="library-toolbar-row library-toolbar-primary">
                <label className="document-search" htmlFor="document-filter">
                    <Search size={15} aria-hidden="true" />
                    <span className="sr-only">Search documents</span>
                    <input
                        id="document-filter"
                        type="search"
                        value={queryInput}
                        onChange={(event) => onQueryInput(event.target.value)}
                        placeholder="Search title or filename…"
                        autoComplete="off"
                        title="Search titles and filenames (press / to focus)"
                    />
                </label>

                <SegmentedControl
                    ariaLabel="Library view"
                    className="library-views"
                    value={view}
                    onChange={onView}
                    options={[
                        { value: 'all', label: 'All', icon: VIEW_ICONS.all, title: 'All documents' },
                        {
                            value: 'favorites',
                            label: `Favorites${viewCounts.favorites ? ` ${viewCounts.favorites}` : ''}`,
                            icon: VIEW_ICONS.favorites,
                            title: 'Starred documents (this browser)',
                        },
                        {
                            value: 'recent',
                            label: 'Recent',
                            icon: VIEW_ICONS.recent,
                            title: 'Recently opened documents (this browser)',
                        },
                    ]}
                />

                <button
                    type="button"
                    className={`library-filters-trigger ${filterCount ? 'is-active' : ''}`}
                    onClick={onOpenFilters}
                    aria-label={`Filters${filterCount ? `, ${filterCount} active` : ''}`}
                    title="Open the filter panel (source, format, review, dates, pages)"
                >
                    <SlidersHorizontal size={14} aria-hidden="true" />
                    <span>Filters</span>
                    {filterCount > 0 && <span className="library-filters-badge">{filterCount}</span>}
                </button>

                <DropdownMenu
                    ariaLabel="Sort documents"
                    align="end"
                    buttonClassName="library-sort-trigger"
                    buttonContent={(
                        <>
                            <span>Sort: {sortLabel(sort, { searching })}</span>
                            <ChevronDown size={14} aria-hidden="true" />
                        </>
                    )}
                    items={sortMenuItems(sort, searching, onSort)}
                />

                <div className="library-toolbar-end">
                    <span
                        className="library-result-count"
                        aria-live="polite"
                        title={narrowed ? `${total} documents match the current filters` : 'Documents in the library'}
                    >
                        {loading
                            ? 'Searching…'
                            : narrowed
                                ? `${total.toLocaleString()} of ${libraryTotal.toLocaleString()}`
                                : `${total.toLocaleString()} document${total === 1 ? '' : 's'}`}
                    </span>
                    <button
                        type="button"
                        className={`library-icon-toggle ${group ? 'is-active' : ''}`}
                        onClick={onToggleGroup}
                        aria-pressed={group}
                        title={group
                            ? 'Grouped by statute family — click for a flat list'
                            : 'Flat list — click to group editions by statute family'}
                    >
                        <FolderTree size={15} aria-hidden="true" />
                    </button>
                    <SegmentedControl
                        ariaLabel="Result density"
                        className="library-density"
                        value={layout}
                        onChange={onLayout}
                        options={[
                            { value: 'list', label: 'List', icon: <Rows3 size={13} />, title: 'List — one row per document' },
                            { value: 'cards', label: 'Grid', icon: <LayoutGrid size={13} />, title: 'Grid — cards with full metadata' },
                            { value: 'compact', label: 'Compact', icon: <List size={13} />, title: 'Compact — dense single-line rows' },
                        ]}
                    />
                    <SavedViewsMenu
                        currentSearch={currentSearch}
                        hasActiveState={Boolean(chips.length) || sort !== 'name'}
                        onApply={onApplySavedView}
                    />
                </div>
            </div>

            {chips.length > 0 && (
                <div className="library-chips" aria-label="Active filters">
                    {chips.map((chip) => (
                        <button
                            key={chip.key}
                            type="button"
                            className="library-chip"
                            onClick={() => onRemoveChip(chip.key)}
                            title={`Remove filter: ${chip.label}`}
                        >
                            {chip.label}
                            <X size={12} aria-hidden="true" />
                        </button>
                    ))}
                    <button type="button" className="library-chip-clear" onClick={onClearAll}>
                        Clear all
                    </button>
                </div>
            )}
        </div>
    );
}
