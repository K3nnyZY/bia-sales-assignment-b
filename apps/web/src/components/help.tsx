import { helpCatalog, type HelpTerm } from "../lib/help";

export function ContextHelp({ term }: { term: HelpTerm }) {
  return (
    <details className="context-help">
      <summary title={helpCatalog[term]} aria-label={`Ayuda sobre ${term}`}>
        ⓘ {term}
      </summary>
      <p>{helpCatalog[term]}</p>
    </details>
  );
}

export function StudioGlossary() {
  return (
    <details className="panel glossary">
      <summary>Guía de conceptos de Agent Studio</summary>
      <dl>
        {Object.entries(helpCatalog).map(([term, text]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd>{text}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
