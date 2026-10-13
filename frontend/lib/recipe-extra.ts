import { API_BASE_URL } from "./api";

export type RecipeExtraBlock =
  | { kind: "heading"; text: string }
  | { kind: "text"; text: string }
  | { kind: "image"; alt: string; src: string };

export function localImageUrl(path: string): string | null {
  const segments = path.replaceAll("\\", "/").split("/");
  if (segments.some((segment) => segment === "" || segment === "." || segment === "..")) {
    return null;
  }
  return `${API_BASE_URL}/recipe-images/${segments.map(encodeURIComponent).join("/")}`;
}

export function parseRecipeExtra(extra: string, images: string[], externalImages: string[]): RecipeExtraBlock[] {
  const blocks: RecipeExtraBlock[] = [];
  const paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length > 0) {
      blocks.push({ kind: "text", text: paragraph.join("\n") });
      paragraph.length = 0;
    }
  };

  for (const sourceLine of extra.split(/\r?\n/)) {
    const line = sourceLine.trim();
    if (!line) {
      flush();
      continue;
    }
    const heading = /^#{1,6}\s+(.+)$/.exec(line);
    if (heading) {
      flush();
      blocks.push({ kind: "heading", text: heading[1] });
      continue;
    }
    const image = /^!\[([^\]]*)\]\(([^)]+)\)$/.exec(line);
    if (image) {
      flush();
      const [, alt, rawPath] = image;
      const basename = rawPath.replaceAll("\\", "/").split("/").at(-1);
      const localPath = images.find((path) => path.replaceAll("\\", "/").split("/").at(-1) === basename);
      const src = localPath ? localImageUrl(localPath) : externalImages.find((url) => url === rawPath && /^https:\/\//i.test(url));
      blocks.push(src ? { kind: "image", alt, src } : { kind: "text", text: `配图暂不可用：${alt || "未命名图片"}` });
      continue;
    }
    paragraph.push(line);
  }
  flush();
  return blocks;
}
