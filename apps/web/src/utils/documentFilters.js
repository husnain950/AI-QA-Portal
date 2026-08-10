export const filterDocuments = (documents, query, sourceFilter) => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return documents
        .filter((document) => {
            const sourceMatches = sourceFilter === 'all'
                || (sourceFilter === 'acts_corpus' && document.source_type === 'acts_corpus')
                || (sourceFilter === 'upload' && document.source_type !== 'acts_corpus');
            const queryMatches = !normalizedQuery
                || document.name.toLocaleLowerCase().includes(normalizedQuery);
            return sourceMatches && queryMatches;
        })
        .sort((left, right) => left.name.localeCompare(right.name));
};
