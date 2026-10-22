/** A corrected release has been published and then re-ingested from corrected files. */
export const isPublished = (status: string) => status === "published" || status === "corrected";
