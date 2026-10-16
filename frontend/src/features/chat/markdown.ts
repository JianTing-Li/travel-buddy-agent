/**
 * A tiny, safe formatter for the agent's replies. Owner: Cheich.
 *
 * It understands only what the agent actually writes: paragraphs, headings, bullet and numbered lists, and
 * **bold**, *italic* and `code`. It returns plain data (never HTML), so rendering it cannot inject markup.
 * Links, images, tables and raw HTML are shown as ordinary text.
 */
export type Inline = { kind: 'text' | 'bold' | 'italic' | 'code'; text: string }

export type Block =
  | { kind: 'heading'; inlines: Inline[] }
  | { kind: 'paragraph'; lines: Inline[][] }
  | { kind: 'list'; ordered: boolean; items: Inline[][] }

const INLINE = /\*\*(.+?)\*\*|`([^`]+)`|\*([^\s*](?:[^*]*[^\s*])?)\*/g
const BULLET = /^\s*[-*•]\s+(.*)$/
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/
const HEADING = /^\s*#{1,6}\s+(.*)$/

export function parseInline(text: string): Inline[] {
  const out: Inline[] = []
  let last = 0
  for (const m of text.matchAll(INLINE)) {
    const start = m.index ?? 0
    if (start > last) out.push({ kind: 'text', text: text.slice(last, start) })
    if (m[1] !== undefined) out.push({ kind: 'bold', text: m[1] })
    else if (m[2] !== undefined) out.push({ kind: 'code', text: m[2] })
    else out.push({ kind: 'italic', text: m[3] })
    last = start + m[0].length
  }
  if (last < text.length) out.push({ kind: 'text', text: text.slice(last) })
  return out
}

export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = []
  let paragraph: Inline[][] = []
  let list: { ordered: boolean; items: Inline[][] } | null = null

  const endParagraph = () => {
    if (paragraph.length) blocks.push({ kind: 'paragraph', lines: paragraph })
    paragraph = []
  }
  const endList = () => {
    if (list) blocks.push({ kind: 'list', ordered: list.ordered, items: list.items })
    list = null
  }

  for (const raw of text.replace(/\r\n?/g, '\n').split('\n')) {
    const line = raw.trimEnd()
    if (!line.trim()) {
      endParagraph()
      endList()
      continue
    }
    const heading = HEADING.exec(line)
    const numbered = NUMBERED.exec(line)
    const bullet = BULLET.exec(line)
    if (heading) {
      endParagraph()
      endList()
      blocks.push({ kind: 'heading', inlines: parseInline(heading[1]) })
    } else if (numbered || bullet) {
      endParagraph()
      const ordered = Boolean(numbered)
      if (list && list.ordered !== ordered) endList()
      if (!list) list = { ordered, items: [] }
      list.items.push(parseInline((numbered ?? bullet)![1]))
    } else {
      endList()
      paragraph.push(parseInline(line.trim()))
    }
  }
  endParagraph()
  endList()
  return blocks
}
