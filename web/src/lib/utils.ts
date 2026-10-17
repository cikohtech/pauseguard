import { createCn } from "cn/config"

// Class merging (clsx + tailwind-merge semantics) that knows this app's theme (index.css): the M3
// type scale (`text-title-m` is a font size, not a colour) and the M3 elevation shadows.
const scale = ["display", "headline", "title", "body", "label"].flatMap((r) => ["l", "m", "s"].map((s) => `${r}-${s}`))

export const cn = createCn({
  extend: {
    classGroups: {
      "font-size": [{ text: scale }],
      shadow: [{ shadow: ["e1", "e2", "e3", "e4", "e5"] }],
    },
  },
})
