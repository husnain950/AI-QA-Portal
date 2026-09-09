function countLeaf(stats, leaf) {
    stats.sectionsCount += 1;
    if (leaf?.html) stats.sectionsWithHtml += 1;
    if (Array.isArray(leaf?.footnotes)) {
        stats.footnoteCount += leaf.footnotes.length;
    }
}

function traverseContainer(stats, node) {
    if (!node || typeof node !== 'object') return;

    for (const section of node.sections || []) {
        countLeaf(stats, section);
    }
    for (const key of ['parts', 'divisions']) {
        for (const child of node[key] || []) {
            const hasChildren = ['sections', 'parts', 'divisions']
                .some((name) => Array.isArray(child?.[name]) && child[name].length > 0);
            if (Object.hasOwn(child || {}, 'html') && !hasChildren) {
                countLeaf(stats, child);
            } else {
                traverseContainer(stats, child);
            }
        }
    }
}

/** Summarise legacy and instrument-shaped pipeline JSON for upload feedback. */
export function summarizeJsonStructure(parsed) {
    const instruments = Array.isArray(parsed?.instruments) ? parsed.instruments : [];
    const chapterRoots = Array.isArray(parsed?.chapters) ? parsed.chapters : [];
    const scheduleRoots = Array.isArray(parsed?.schedules) ? parsed.schedules : [];
    const stats = {
        instrumentsCount: instruments.length,
        chaptersCount: chapterRoots.length,
        schedulesCount: scheduleRoots.length,
        sectionsCount: 0,
        sectionsWithHtml: 0,
        footnoteCount: 0,
    };

    const roots = [...chapterRoots, ...scheduleRoots];
    for (const instrument of instruments) {
        const chapters = Array.isArray(instrument?.chapters) ? instrument.chapters : [];
        const schedules = Array.isArray(instrument?.schedules) ? instrument.schedules : [];
        stats.chaptersCount += chapters.length;
        stats.schedulesCount += schedules.length;
        roots.push(...chapters, ...schedules);
    }
    roots.forEach((root) => traverseContainer(stats, root));
    return stats;
}
