import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '../../utils/cn'

/**
 * Renderizador de Markdown optimizado para dashboards técnicos
 * - Usa todo el ancho disponible
 * - Sin límites por caracteres
 * - Texto y marcadores forzados a blanco
 * - Sin estilos heredados tipo "prose"
 */
export function MarkdownRenderer({ content, className }) {
  return (
    <div className={cn('w-full max-w-full overflow-hidden', className)}>
      <div className="space-y-3 break-words text-white">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ ...props }) => (
              <h1
                className="text-2xl font-bold text-white mt-8 mb-4 border-b border-dark-border-primary/50 pb-2 first:mt-0"
                {...props}
              />
            ),
            h2: ({ ...props }) => (
              <h2
                className="text-xl font-bold text-white mt-8 mb-4 first:mt-0 items-center flex gap-2"
                {...props}
              />
            ),
            h3: ({ ...props }) => (
              <h3
                className="text-lg font-semibold text-white mt-6 mb-3"
                {...props}
              />
            ),

            p: ({ ...props }) => (
              <p
                className="text-[15px] text-gray-200 leading-relaxed mb-4 last:mb-0"
                {...props}
              />
            ),

            ul: ({ ...props }) => (
              <ul
                className="list-disc list-outside ml-6 mb-4 space-y-2 text-[15px] text-gray-200"
                {...props}
              />
            ),

            ol: ({ ...props }) => (
              <ol
                className="list-decimal list-outside ml-6 mb-4 space-y-2 text-[15px] text-gray-200"
                {...props}
              />
            ),

            li: ({ ...props }) => (
              <li
                className="leading-relaxed pl-1 marker:text-dark-accent-primary marker:font-bold"
                {...props}
              />
            ),

            strong: ({ ...props }) => (
              <strong className="font-bold text-white" {...props} />
            ),

            em: ({ ...props }) => (
              <em className="italic text-gray-400" {...props} />
            ),

            code: ({ inline, ...props }) =>
              inline ? (
                <code
                  className="font-bold text-white break-words"
                  {...props}
                />
              ) : (
                <code
                  className="block p-4 bg-dark-surface-secondary text-gray-200 rounded-lg text-sm font-mono overflow-x-auto mb-4 border border-dark-border-primary/30 w-full"
                  {...props}
                />
              ),

            pre: ({ ...props }) => (
              <pre
                className="bg-dark-surface-secondary rounded-lg overflow-hidden mb-6 border border-dark-border-primary/30 w-full"
                {...props}
              />
            ),

            blockquote: ({ ...props }) => (
              <blockquote
                className="border-l-4 border-dark-accent-primary pl-4 py-1 my-6 italic text-gray-400 bg-dark-surface-secondary/20 rounded-r-lg"
                {...props}
              />
            ),

            a: ({ ...props }) => (
              <a
                className="text-dark-accent-secondary hover:text-dark-accent-hover underline decoration-dark-accent-secondary/30 hover:decoration-dark-accent-hover underline-offset-4 transition-all"
                target="_blank"
                rel="noopener noreferrer"
                {...props}
              />
            ),

            hr: ({ ...props }) => (
              <hr className="border-dark-border-primary/50 my-8" {...props} />
            ),

            table: ({ ...props }) => (
              <div className="overflow-x-auto my-6 w-full border border-dark-border-primary/40 rounded-lg">
                <table className="w-full text-left border-collapse" {...props} />
              </div>
            ),

            thead: ({ ...props }) => (
              <thead className="bg-dark-surface-secondary border-b border-dark-border-primary/40" {...props} />
            ),

            th: ({ ...props }) => (
              <th
                className="px-6 py-3 text-xs font-bold text-gray-400 uppercase tracking-wider whitespace-nowrap"
                {...props}
              />
            ),

            td: ({ ...props }) => (
              <td
                className="px-6 py-4 text-sm text-gray-300 border-b border-dark-border-primary/20 last:border-0"
                {...props}
              />
            ),

            tr: ({ ...props }) => (
              <tr
                className="hover:bg-dark-surface-hover/30 transition-colors"
                {...props}
              />
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  )
}
