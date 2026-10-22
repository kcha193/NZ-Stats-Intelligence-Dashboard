/** Starts a browser download of a data or object URL. */
export function saveFile(href: string, filename: string) {
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.click();
}
