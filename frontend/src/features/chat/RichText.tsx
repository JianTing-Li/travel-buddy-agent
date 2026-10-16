/** Shows an agent reply with light formatting. Owner: Cheich. Builds React elements only, never raw HTML. */
import { Fragment } from 'react'
import { parseBlocks, type Inline } from './markdown.ts'

function Inlines({ parts }: { parts: Inline[] }) {
  return (
    <>
      {parts.map((p, i) =>
        p.kind === 'bold' ? <strong key={i}>{p.text}</strong>
        : p.kind === 'italic' ? <em key={i}>{p.text}</em>
        : p.kind === 'code' ? <code key={i}>{p.text}</code>
        : <Fragment key={i}>{p.text}</Fragment>,
      )}
    </>
  )
}

export function RichText({ text }: { text: string }) {
  return (
    <>
      {parseBlocks(text).map((block, i) => {
        if (block.kind === 'heading') {
          return <p key={i} className="chat-heading"><Inlines parts={block.inlines} /></p>
        }
        if (block.kind === 'list') {
          const items = block.items.map((item, j) => <li key={j}><Inlines parts={item} /></li>)
          return block.ordered ? <ol key={i}>{items}</ol> : <ul key={i}>{items}</ul>
        }
        return (
          <p key={i}>
            {block.lines.map((line, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                <Inlines parts={line} />
              </Fragment>
            ))}
          </p>
        )
      })}
    </>
  )
}
