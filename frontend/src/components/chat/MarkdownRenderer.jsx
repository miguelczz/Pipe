import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '../../utils/cn'

/**
 * Componente para renderizar markdown de forma agradable
 */
export function MarkdownRenderer({ content, className }) {
  return (
    <div className={cn('prose prose-invert max-w-none overflow-hidden min-w-0', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
        // Personalizar estilos de los elementos markdown
        h1: ({ ...props }) => (
          <h1 className="text-2xl font-semibold text-dark-text-primary mt-4 mb-2 first:mt-0" {...props} />
        ),
        h2: ({ ...props }) => (
          <h2 className="text-xl font-semibold text-dark-text-primary mt-4 mb-2 first:mt-0" {...props} />
        ),
        h3: ({ ...props }) => (
          <h3 className="text-lg font-medium text-dark-text-primary mt-3 mb-2 first:mt-0" {...props} />
        ),
        p: ({ ...props }) => (
          <p className="text-[15px] text-dark-text-primary leading-relaxed mb-2 last:mb-0" {...props} />
        ),
        ul: ({ ...props }) => (
          <ul className="list-disc list-inside mb-2 space-y-1 text-[15px] text-dark-text-primary" {...props} />
        ),
        ol: ({ ...props }) => (
          <ol className="mb-2 space-y-1 text-[15px] text-dark-text-primary" {...props} />
        ),
        li: ({ ...props }) => (
          <li className="text-[15px] text-dark-text-primary leading-relaxed" {...props} />
        ),
        strong: ({ ...props }) => (
          <strong className="font-semibold text-dark-text-primary" {...props} />
        ),
        em: ({ ...props }) => (
          <em className="italic text-dark-text-secondary" {...props} />
        ),
        code: ({ inline, ...props }) => {
          if (inline) {
            return (
              <code
                className="px-1.5 py-0.5 bg-dark-surface-secondary text-dark-accent-primary rounded text-sm font-mono border border-dark-border-primary/20 break-words"
                {...props}
              />
            )
          }
          return (
            <code
              className="block p-3 bg-dark-surface-secondary text-dark-text-primary rounded-lg text-sm font-mono overflow-x-auto mb-2 border border-dark-border-primary/20 break-words"
              style={{ maxWidth: '100%', wordBreak: 'break-word' }}
              {...props}
            />
          )
        },
        pre: ({ ...props }) => (
          <pre className="bg-dark-surface-secondary rounded-lg p-3 overflow-x-auto mb-2 -mx-2 sm:mx-0" style={{ maxWidth: 'calc(100vw - 2rem)' }} {...props} />
        ),
        blockquote: ({ ...props }) => (
          <blockquote
            className="border-l-4 border-dark-accent-primary pl-4 italic text-dark-text-secondary my-2 bg-dark-surface-secondary/30 rounded-r-lg py-2"
            {...props}
          />
        ),
        a: ({ ...props }) => (
          <a
            className="text-dark-accent-primary hover:text-dark-accent-hover underline"
            target="_blank"
            rel="noopener noreferrer"
            {...props}
          />
        ),
        hr: ({ ...props }) => (
          <hr className="border-dark-border-primary my-4" {...props} />
        ),
        table: ({ ...props }) => (
          <div className="overflow-x-auto my-3 -mx-2 sm:mx-0" style={{ maxWidth: 'calc(100vw - 2rem)' }}>
            <table className="w-full border-collapse min-w-[400px]" {...props} />
          </div>
        ),
        thead: ({ ...props }) => (
          <thead className="bg-dark-surface-secondary" {...props} />
        ),
        th: ({ ...props }) => (
          <th
            className="px-4 py-2.5 text-left text-sm font-semibold text-dark-text-primary border-b border-dark-border-primary/50"
            {...props}
          />
        ),
        td: ({ ...props }) => (
          <td
            className="px-4 py-2.5 text-sm text-dark-text-secondary border-b border-dark-border-primary/30"
            {...props}
          />
        ),
        tr: ({ ...props }) => (
          <tr className="hover:bg-dark-surface-hover/50 transition-colors" {...props} />
        ),
      }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

