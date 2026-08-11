import { useEffect, useRef } from 'react';

function focusables(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-focusable="true"]'))
    .filter((el) => !el.hasAttribute('disabled') && el.offsetParent !== null);
}

function moveFocus(delta: number) {
  const items = focusables();
  if (!items.length) return;
  const current = document.activeElement as HTMLElement | null;
  let index = items.indexOf(current as HTMLElement);
  if (index < 0) index = delta > 0 ? -1 : 0;
  index = (index + delta + items.length) % items.length;
  items[index].focus({ preventScroll: true });
}

function activateFocus() {
  const current = document.activeElement as HTMLElement | null;
  if (current?.matches('[data-focusable="true"]')) current.click();
}

export function useGameNavigation(onBack: () => void, onTab?: (delta: number) => void) {
  const lastButtons = useRef<boolean[]>([]);
  const lastMove = useRef(0);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const editing = target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.tagName === 'SELECT';
      if (editing && event.key !== 'Escape') return;

      if (['ArrowRight', 'ArrowDown', 'd', 'D', 's', 'S'].includes(event.key)) {
        event.preventDefault(); moveFocus(1);
      } else if (['ArrowLeft', 'ArrowUp', 'a', 'A', 'w', 'W'].includes(event.key)) {
        event.preventDefault(); moveFocus(-1);
      } else if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault(); activateFocus();
      } else if (event.key === 'Escape' || event.key === 'Backspace') {
        event.preventDefault(); onBack();
      } else if (event.key === 'q' || event.key === 'Q') {
        onTab?.(-1);
      } else if (event.key === 'e' || event.key === 'E') {
        onTab?.(1);
      }
    };

    window.addEventListener('keydown', onKey);
    const first = focusables()[0];
    if (first && !document.activeElement?.matches('[data-focusable="true"]')) first.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [onBack, onTab]);

  useEffect(() => {
    let raf = 0;
    const poll = () => {
      const pad = navigator.getGamepads?.().find(Boolean);
      if (pad) {
        const pressed = pad.buttons.map((b) => b.pressed);
        const now = performance.now();
        const edge = (i: number) => pressed[i] && !lastButtons.current[i];
        const axisX = pad.axes[0] ?? 0;
        const axisY = pad.axes[1] ?? 0;
        const directional = pressed[12] || pressed[13] || pressed[14] || pressed[15] || Math.abs(axisX) > .62 || Math.abs(axisY) > .62;

        if (directional && now - lastMove.current > 180) {
          if (pressed[15] || pressed[13] || axisX > .62 || axisY > .62) moveFocus(1);
          else if (pressed[14] || pressed[12] || axisX < -.62 || axisY < -.62) moveFocus(-1);
          lastMove.current = now;
        }
        if (edge(0)) activateFocus();
        if (edge(1)) onBack();
        if (edge(4)) onTab?.(-1);
        if (edge(5)) onTab?.(1);
        lastButtons.current = pressed;
      }
      raf = requestAnimationFrame(poll);
    };
    raf = requestAnimationFrame(poll);
    return () => cancelAnimationFrame(raf);
  }, [onBack, onTab]);
}

export function focusOnHover(event: React.MouseEvent<HTMLElement>) {
  event.currentTarget.focus({ preventScroll: true });
}
