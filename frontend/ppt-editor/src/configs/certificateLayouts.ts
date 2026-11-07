import { nanoid } from "nanoid";
import type { Slide } from "@/types/slides";
import classic from "./certificate-layouts/classic-blue.json";
import minimal from "./certificate-layouts/minimal.json";
import evergreen from "./certificate-layouts/evergreen.json";

// Reuse examples/templates. The red variant changes the blue layout's palette.
const red = JSON.parse(
  JSON.stringify(classic)
    .replaceAll("#173B64", "#8B1E24")
    .replaceAll("#C69A4E", "#B88632")
);
for (const element of red.presentation.slides[0].elements) {
  if (
    element.type === "image" &&
    element.src?.startsWith("data:image/svg+xml;base64,")
  ) {
    const svg = atob(element.src.split(",")[1])
      .replaceAll("#173B64", "#8B1E24")
      .replaceAll("#C69A4E", "#B88632");
    element.src = "data:image/svg+xml;base64," + btoa(svg);
  }
}
export const CERTIFICATE_LAYOUTS = [
  {
    id: "red-gold",
    name: "经典红金",
    description: "传统荣誉证书",
    document: red
  },
  {
    id: "classic-blue",
    name: "典雅蓝金",
    description: "荣誉与表彰",
    document: classic
  },
  {
    id: "minimal",
    name: "简约留白",
    description: "通用获奖证书",
    document: minimal
  },
  {
    id: "evergreen",
    name: "清新青绿",
    description: "创新与学科竞赛",
    document: evergreen
  }
];

export function certificateLayout(
  id: string,
  width: number,
  height: number
): Slide {
  const preset = CERTIFICATE_LAYOUTS.find(item => item.id === id)!;
  const slide = JSON.parse(
    JSON.stringify(preset.document.presentation.slides[0])
  ) as Slide;
  const sx = width / preset.document.page.width,
    sy = height / preset.document.page.height,
    scale = Math.min(sx, sy);
  slide.id = nanoid(10);
  for (const element of slide.elements) {
    element.id = nanoid(10);
    element.left *= sx;
    element.top *= sy;
    element.width *= sx;
    if ("height" in element) element.height *= sy;
    if (element.type === "line") {
      element.start = [element.start[0] * sx, element.start[1] * sy];
      element.end = [element.end[0] * sx, element.end[1] * sy];
    }
    if (element.type === "text") {
      element.content = element.content
        .replace("SAMPLE · 演示证书", "证书编号：{{number}}")
        .replace(
          /font-size:\s*([\d.]+)(px|pt)/g,
          (_, size, unit) =>
            `font-size:${+(Number(size) * scale).toFixed(2)}${unit}`
        );
      if (element.paragraphSpace) element.paragraphSpace *= scale;
    }
  }
  return slide;
}
