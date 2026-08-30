import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { Button, IconButton } from './Button';

type DialogSize = 'sm' | 'md' | 'lg';

export interface DialogProps {
  readonly open: boolean;
  readonly title: ReactNode;
  readonly description?: ReactNode;
  readonly eyebrow?: ReactNode;
  readonly children?: ReactNode;
  readonly footer?: ReactNode;
  readonly size?: DialogSize;
  readonly closeLabel?: string;
  readonly closeDisabled?: boolean;
  readonly onClose: () => void;
}

const FOCUSABLE_SELECTOR = [
  '[data-dialog-initial-focus]',
  'button:not(:disabled)',
  'input:not(:disabled)',
  'select:not(:disabled)',
  'textarea:not(:disabled)',
  'a[href]',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

/** Accessible modal foundation with focus trapping, Escape handling, and focus restoration. */
export function Dialog({
  open,
  title,
  description,
  eyebrow,
  children,
  footer,
  size = 'md',
  closeLabel = '닫기',
  closeDisabled = false,
  onClose,
}: DialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLElement>(null);
  const onCloseRef = useRef(onClose);
  const closeDisabledRef = useRef(closeDisabled);

  useEffect(() => {
    onCloseRef.current = onClose;
    closeDisabledRef.current = closeDisabled;
  }, [closeDisabled, onClose]);

  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const panel = panelRef.current;
    const focusTimer = window.setTimeout(() => {
      const initialFocus = panel?.querySelector<HTMLElement>('[data-dialog-initial-focus]')
        ?? panel?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
      initialFocus?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (!closeDisabledRef.current) {
          event.preventDefault();
          onCloseRef.current();
        }
        return;
      }
      if (event.key !== 'Tab' || !panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
        .filter((element) => element.getAttribute('aria-hidden') !== 'true');
      if (focusable.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener('keydown', handleKeyDown);
      previousFocus?.focus();
    };
  }, [open]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="ui-dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !closeDisabled) onClose();
      }}
    >
      <section
        ref={panelRef}
        className={`ui-dialog ui-dialog--${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
      >
        <header className="ui-dialog__header">
          <div>
            {eyebrow ? <span className="ui-dialog__eyebrow">{eyebrow}</span> : null}
            <h2 id={titleId}>{title}</h2>
            {description ? <p id={descriptionId}>{description}</p> : null}
          </div>
          <IconButton
            size="sm"
            variant="ghost"
            aria-label={closeLabel}
            onClick={onClose}
            disabled={closeDisabled}
          >
            <X size={18} />
          </IconButton>
        </header>
        {children ? <div className="ui-dialog__body">{children}</div> : null}
        {footer ? <footer className="ui-dialog__footer">{footer}</footer> : null}
      </section>
    </div>,
    document.body,
  );
}

export interface ConfirmDialogProps {
  readonly open: boolean;
  readonly title: ReactNode;
  readonly description?: ReactNode;
  readonly detail?: ReactNode;
  readonly confirmLabel?: string;
  readonly cancelLabel?: string;
  readonly tone?: 'default' | 'danger';
  readonly busy?: boolean;
  readonly error?: ReactNode;
  readonly onClose: () => void;
  readonly onConfirm: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  detail,
  confirmLabel = '확인',
  cancelLabel = '취소',
  tone = 'default',
  busy = false,
  error,
  onClose,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      size="sm"
      eyebrow={tone === 'danger' ? 'DESTRUCTIVE ACTION' : 'CONFIRM ACTION'}
      title={title}
      description={description}
      closeDisabled={busy}
      onClose={onClose}
      footer={(
        <>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={busy}
            data-dialog-initial-focus={tone === 'danger' ? true : undefined}
          >
            {cancelLabel}
          </Button>
          <Button
            variant={tone === 'danger' ? 'danger-solid' : 'primary'}
            busy={busy}
            onClick={onConfirm}
            disabled={busy}
            data-dialog-initial-focus={tone === 'default' ? true : undefined}
          >
            {busy ? '처리 중...' : confirmLabel}
          </Button>
        </>
      )}
    >
      {detail ? <div className="ui-dialog__detail">{detail}</div> : null}
      {error ? <div className="ui-dialog__error" role="alert">{error}</div> : null}
    </Dialog>
  );
}

export interface PromptDialogProps {
  readonly open: boolean;
  readonly title: ReactNode;
  readonly description?: ReactNode;
  readonly label: string;
  readonly initialValue?: string;
  readonly placeholder?: string;
  readonly confirmLabel?: string;
  readonly cancelLabel?: string;
  readonly busy?: boolean;
  readonly error?: ReactNode;
  readonly maxLength?: number;
  readonly onClose: () => void;
  readonly onConfirm: (value: string) => void;
}

export function PromptDialog({
  open,
  title,
  description,
  label,
  initialValue = '',
  placeholder,
  confirmLabel = '확인',
  cancelLabel = '취소',
  busy = false,
  error,
  maxLength = 80,
  onClose,
  onConfirm,
}: PromptDialogProps) {
  const [value, setValue] = useState(initialValue);
  const formId = useId();
  const inputId = useId();

  useEffect(() => {
    if (open) setValue(initialValue);
  }, [initialValue, open]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    onConfirm(trimmed);
  };

  return (
    <Dialog
      open={open}
      size="sm"
      eyebrow="CREATE WORKFLOW"
      title={title}
      description={description}
      closeDisabled={busy}
      onClose={onClose}
      footer={(
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{cancelLabel}</Button>
          <Button
            variant="primary"
            type="submit"
            form={formId}
            busy={busy}
            disabled={busy || value.trim().length === 0}
          >
            {busy ? '생성 중...' : confirmLabel}
          </Button>
        </>
      )}
    >
      <form id={formId} className="ui-dialog__form" onSubmit={submit}>
        <label htmlFor={inputId}>{label}</label>
        <input
          id={inputId}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={placeholder}
          maxLength={maxLength}
          disabled={busy}
          data-dialog-initial-focus
        />
      </form>
      {error ? <div className="ui-dialog__error" role="alert">{error}</div> : null}
    </Dialog>
  );
}
