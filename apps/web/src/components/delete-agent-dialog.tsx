"use client";

import { useEffect, useRef } from "react";

export function DeleteAgentDialog({
  name,
  busy,
  cancel,
  confirm,
}: {
  name: string;
  busy: boolean;
  cancel: () => void;
  confirm: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      aria-labelledby="delete-agent-title"
      aria-describedby="delete-agent-warning"
      onCancel={(event) => {
        if (busy) event.preventDefault();
        else cancel();
      }}
    >
      <h2 id="delete-agent-title">Eliminar agente</h2>
      <p id="delete-agent-warning">
        Vas a eliminar <strong>{name}</strong>. Esta acción es irreversible.
        Se retirará del inventario, conservando la auditoría y los borradores
        descartados. El backend comprobará que eres administrador y que no
        existe ningún snapshot congelado.
      </p>
      <div className="actions">
        <button className="secondary" disabled={busy} onClick={cancel} autoFocus>
          Cancelar
        </button>
        <button className="danger" disabled={busy} onClick={confirm}>
          {busy ? "Eliminando…" : "Eliminar definitivamente"}
        </button>
      </div>
    </dialog>
  );
}
