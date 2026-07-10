const fs = require("fs");
const path = require("path");
const {
  AlignmentType,
  BorderStyle,
  Document,
  ExternalHyperlink,
  Footer,
  Header,
  HeadingLevel,
  LevelFormat,
  PageBreak,
  PageNumber,
  Packer,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableOfContents,
  TableRow,
  TextRun,
  VerticalAlign,
  WidthType,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const OUTPUT = path.join(ROOT, "docs", "创非凡数智名片_开发基线_v1.0.docx");
const INPUTS = [
  "docs/01-需求基线.md",
  "docs/02-系统架构.md",
  "docs/03-数据与权限.md",
  "docs/04-API契约.md",
  "docs/05-AI-RAG与安全.md",
  "docs/06-开发计划与验收.md",
  "docs/07-工程规范.md",
  "docs/08-决策与待确认.md",
  "docs/09-需求追踪矩阵.md",
  "docs/10-样板企业资料采集模板.md",
];

const COLORS = {
  navy: "17365D",
  blue: "1F4E78",
  lightBlue: "DDEBF7",
  paleBlue: "EDF4FB",
  text: "1F2937",
  muted: "5B6573",
  border: "B8C4D0",
  code: "F4F6F8",
  white: "FFFFFF",
};

const TABLE_WIDTH = 9020;
const tableBorder = { style: BorderStyle.SINGLE, size: 2, color: COLORS.border };
const tableBorders = {
  top: tableBorder,
  bottom: tableBorder,
  left: tableBorder,
  right: tableBorder,
  insideHorizontal: tableBorder,
  insideVertical: tableBorder,
};

let listCounter = 0;
const numberingConfigs = [];

function nextListReference(kind) {
  const reference = `${kind}-${++listCounter}`;
  numberingConfigs.push({
    reference,
    levels: [
      {
        level: 0,
        format: kind === "bullet" ? LevelFormat.BULLET : LevelFormat.DECIMAL,
        text: kind === "bullet" ? "•" : "%1.",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 600, hanging: 300 } } },
      },
    ],
  });
  return reference;
}

function cleanPlainText(text) {
  return text
    .replace(/\\\|/g, "|")
    .replace(/<br\s*\/?\s*>/gi, "；")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1（$2）");
}

function inlineChildren(text, options = {}) {
  const children = [];
  const pattern = /(\*\*.*?\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)]+\))/g;
  let cursor = 0;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      children.push(new TextRun({ text: text.slice(cursor, match.index), ...options }));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      children.push(new TextRun({ text: token.slice(2, -2), bold: true, ...options }));
    } else if (token.startsWith("`")) {
      children.push(
        new TextRun({
          text: token.slice(1, -1),
          font: "Consolas",
          color: COLORS.blue,
          ...options,
        }),
      );
    } else {
      const linkMatch = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
      if (linkMatch) {
        children.push(
          new ExternalHyperlink({
            link: linkMatch[2],
            children: [new TextRun({ text: linkMatch[1], style: "Hyperlink", ...options })],
          }),
        );
      }
    }
    cursor = pattern.lastIndex;
  }
  if (cursor < text.length) {
    children.push(new TextRun({ text: text.slice(cursor), ...options }));
  }
  return children.length ? children : [new TextRun({ text: "", ...options })];
}

function splitMarkdownRow(line) {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  const cells = [];
  let current = "";
  let escaped = false;
  for (const char of trimmed) {
    if (escaped) {
      current += char;
      escaped = false;
    } else if (char === "\\") {
      escaped = true;
    } else if (char === "|") {
      cells.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }
  cells.push(current.trim());
  return cells;
}

function isTableSeparator(line) {
  const cells = splitMarkdownRow(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function computeColumnWidths(rows) {
  const count = Math.max(...rows.map((row) => row.length));
  const weights = Array(count).fill(1);
  for (const row of rows.slice(0, 20)) {
    for (let i = 0; i < count; i += 1) {
      const length = cleanPlainText(row[i] || "").length;
      weights[i] = Math.max(weights[i], Math.min(length, 32));
    }
  }
  const minimum = 900;
  const available = TABLE_WIDTH - minimum * count;
  const totalWeight = weights.reduce((a, b) => a + b, 0);
  const widths = weights.map((weight) => minimum + Math.floor((available * weight) / totalWeight));
  widths[widths.length - 1] += TABLE_WIDTH - widths.reduce((a, b) => a + b, 0);
  return widths;
}

function tableCell(text, width, isHeader) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    borders: tableBorders,
    shading: isHeader ? { fill: COLORS.blue, type: ShadingType.CLEAR } : undefined,
    verticalAlign: VerticalAlign.CENTER,
    margins: { top: 90, bottom: 90, left: 120, right: 120 },
    children: [
      new Paragraph({
        spacing: { before: 0, after: 0, line: 270 },
        children: inlineChildren(text, {
          size: 18,
          bold: isHeader,
          color: isHeader ? COLORS.white : COLORS.text,
          font: "Microsoft YaHei",
        }),
      }),
    ],
  });
}

function markdownTable(rows) {
  const normalizedWidth = Math.max(...rows.map((row) => row.length));
  const normalized = rows.map((row) => [...row, ...Array(normalizedWidth - row.length).fill("")]);
  const widths = computeColumnWidths(normalized);
  return new Table({
    width: { size: TABLE_WIDTH, type: WidthType.DXA },
    columnWidths: widths,
    margins: { top: 90, bottom: 90, left: 120, right: 120 },
    rows: normalized.map(
      (row, rowIndex) =>
        new TableRow({
          tableHeader: rowIndex === 0,
          cantSplit: true,
          children: row.map((cell, cellIndex) => tableCell(cell, widths[cellIndex], rowIndex === 0)),
        }),
    ),
  });
}

function codeParagraph(text, isFirst, language) {
  const prefix = isFirst && language ? `[${language}] ` : "";
  return new Paragraph({
    spacing: { before: isFirst ? 120 : 0, after: 0, line: 240 },
    shading: { fill: COLORS.code, type: ShadingType.CLEAR },
    indent: { left: 240, right: 240 },
    children: [
      new TextRun({
        text: `${prefix}${text || " "}`,
        font: "Consolas",
        size: 17,
        color: COLORS.text,
      }),
    ],
  });
}

function paragraphForHeading(level, text, pageBreakBefore = false) {
  const headingMap = {
    1: HeadingLevel.HEADING_1,
    2: HeadingLevel.HEADING_2,
    3: HeadingLevel.HEADING_3,
    4: HeadingLevel.HEADING_4,
  };
  return new Paragraph({
    heading: headingMap[Math.min(level, 4)],
    pageBreakBefore,
    keepNext: true,
    children: inlineChildren(text),
  });
}

function parseMarkdown(markdown, pageBreakOnH1) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const children = [];
  let index = 0;
  let listState = null;
  let inCode = false;
  let codeLanguage = "";
  let firstCodeLine = false;

  while (index < lines.length) {
    const raw = lines[index];
    const line = raw.trimEnd();

    if (line.startsWith("```")) {
      if (!inCode) {
        inCode = true;
        codeLanguage = line.slice(3).trim();
        firstCodeLine = true;
      } else {
        inCode = false;
        codeLanguage = "";
        children.push(new Paragraph({ spacing: { after: 80 }, children: [new TextRun("")] }));
      }
      listState = null;
      index += 1;
      continue;
    }

    if (inCode) {
      children.push(codeParagraph(raw, firstCodeLine, codeLanguage));
      firstCodeLine = false;
      index += 1;
      continue;
    }

    if (line.trim().startsWith("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const rows = [splitMarkdownRow(line)];
      index += 2;
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        rows.push(splitMarkdownRow(lines[index]));
        index += 1;
      }
      children.push(markdownTable(rows));
      children.push(new Paragraph({ spacing: { after: 100 }, children: [new TextRun("")] }));
      listState = null;
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      children.push(paragraphForHeading(level, heading[2], pageBreakOnH1 && level === 1));
      pageBreakOnH1 = false;
      listState = null;
      index += 1;
      continue;
    }

    const bullet = line.match(/^\s*-\s+(.+)$/);
    const numbered = line.match(/^\s*\d+\.\s+(.+)$/);
    if (bullet || numbered) {
      const kind = bullet ? "bullet" : "numbered";
      if (!listState || listState.kind !== kind) {
        listState = { kind, reference: nextListReference(kind) };
      }
      const content = (bullet || numbered)[1];
      children.push(
        new Paragraph({
          numbering: { reference: listState.reference, level: 0 },
          spacing: { before: 30, after: 30, line: 300 },
          children: inlineChildren(content, { size: 21, color: COLORS.text, font: "Microsoft YaHei" }),
        }),
      );
      index += 1;
      continue;
    }

    if (!line.trim()) {
      listState = null;
      index += 1;
      continue;
    }

    const quote = line.match(/^>\s?(.*)$/);
    if (quote) {
      children.push(
        new Paragraph({
          indent: { left: 360 },
          border: { left: { style: BorderStyle.SINGLE, size: 16, color: COLORS.blue, space: 8 } },
          shading: { fill: COLORS.paleBlue, type: ShadingType.CLEAR },
          spacing: { before: 80, after: 80, line: 300 },
          children: inlineChildren(quote[1], { size: 21, italics: true, color: COLORS.muted }),
        }),
      );
      listState = null;
      index += 1;
      continue;
    }

    children.push(
      new Paragraph({
        spacing: { before: 40, after: 80, line: 320 },
        children: inlineChildren(line.trim(), { size: 21, color: COLORS.text, font: "Microsoft YaHei" }),
      }),
    );
    listState = null;
    index += 1;
  }

  return children;
}

function coverChildren() {
  return [
    new Paragraph({ spacing: { before: 2200, after: 200 }, children: [new TextRun("")] }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 },
      children: [
        new TextRun({ text: "创非凡数智名片", bold: true, size: 54, color: COLORS.navy, font: "Microsoft YaHei" }),
      ],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 720 },
      children: [
        new TextRun({ text: "开发基线与系统架构文档", bold: true, size: 38, color: COLORS.blue, font: "Microsoft YaHei" }),
      ],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 160 },
      children: [new TextRun({ text: "版本 V1.0", size: 24, color: COLORS.muted, font: "Microsoft YaHei" })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 160 },
      children: [new TextRun({ text: "基线日期：2026-07-10", size: 24, color: COLORS.muted, font: "Microsoft YaHei" })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 650, after: 120 },
      children: [
        new TextRun({
          text: "依据：开发需求说明书（2026-07-06）、技术方案评审稿（2026-07-08）、详细开发文档（2026-07-10）",
          size: 20,
          color: COLORS.muted,
          font: "Microsoft YaHei",
        }),
      ],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        new TextRun({
          text: "用途：开发启动、技术评审、任务拆分与阶段验收",
          size: 20,
          color: COLORS.muted,
          font: "Microsoft YaHei",
        }),
      ],
    }),
    new Paragraph({ children: [new PageBreak()] }),
    new Paragraph({
      heading: HeadingLevel.HEADING_1,
      children: [new TextRun("目录")],
    }),
    new TableOfContents("", { hyperlink: true, headingStyleRange: "1-3" }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

function buildChildren() {
  const children = [...coverChildren()];
  for (const input of INPUTS) {
    const absolute = path.join(ROOT, input);
    const markdown = fs.readFileSync(absolute, "utf8");
    children.push(...parseMarkdown(markdown, true));
  }
  return children;
}

async function main() {
  const children = buildChildren();
  const doc = new Document({
    creator: "Codex",
    title: "创非凡数智名片开发基线与系统架构文档",
    subject: "开发启动、系统架构、数据、API、RAG、计划与验收",
    description: "由三份项目源文档交叉梳理形成的开发基线。",
    numbering: { config: numberingConfigs },
    styles: {
      default: {
        document: { run: { font: "Microsoft YaHei", size: 21, color: COLORS.text } },
      },
      paragraphStyles: [
        {
          id: "Title",
          name: "Title",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { font: "Microsoft YaHei", size: 54, bold: true, color: COLORS.navy },
          paragraph: { alignment: AlignmentType.CENTER, spacing: { before: 240, after: 240 }, outlineLevel: 0 },
        },
        {
          id: "Heading1",
          name: "Heading 1",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { font: "Microsoft YaHei", size: 34, bold: true, color: COLORS.navy },
          paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 0, keepNext: true },
        },
        {
          id: "Heading2",
          name: "Heading 2",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { font: "Microsoft YaHei", size: 29, bold: true, color: COLORS.blue },
          paragraph: { spacing: { before: 280, after: 140 }, outlineLevel: 1, keepNext: true },
        },
        {
          id: "Heading3",
          name: "Heading 3",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { font: "Microsoft YaHei", size: 25, bold: true, color: COLORS.text },
          paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 2, keepNext: true },
        },
        {
          id: "Heading4",
          name: "Heading 4",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { font: "Microsoft YaHei", size: 22, bold: true, color: COLORS.text },
          paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 3, keepNext: true },
        },
      ],
    },
    sections: [
      {
        properties: {
          page: {
            size: { width: 11906, height: 16838 },
            margin: { top: 1080, right: 1080, bottom: 1080, left: 1080, header: 520, footer: 520 },
          },
        },
        headers: {
          default: new Header({
            children: [
              new Paragraph({
                alignment: AlignmentType.RIGHT,
                border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: COLORS.lightBlue, space: 4 } },
                children: [
                  new TextRun({
                    text: "创非凡数智名片 · 开发基线 V1.0",
                    size: 16,
                    color: COLORS.muted,
                    font: "Microsoft YaHei",
                  }),
                ],
              }),
            ],
          }),
        },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [
                  new TextRun({ text: "第 ", size: 16, color: COLORS.muted }),
                  new TextRun({ children: [PageNumber.CURRENT], size: 16, color: COLORS.muted }),
                  new TextRun({ text: " 页", size: 16, color: COLORS.muted }),
                ],
              }),
            ],
          }),
        },
        children,
      },
    ],
  });

  fs.mkdirSync(path.dirname(OUTPUT), { recursive: true });
  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(OUTPUT, buffer);
  console.log(`generated: ${OUTPUT}`);
  console.log(`bytes: ${buffer.length}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
