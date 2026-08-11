import { useEffect, useRef, type ReactNode } from 'react';
import {
  init,
  navigateByDirection,
  setFocus,
  useFocusable,
} from '@noriginmedia/norigin-spatial-navigation';

let initialized = false;
if (!initialized) {
  init({
    debug: false,
    visualDebug: false,
    distanceCalculationMethod: 'center',
  });
  initialized = true;
}

type SpatialButtonProps = {
  focusKey: string;
  className?: string;
  children: ReactNode | ((focused: boolean) => ReactNode);
  onPress?: () => void;
  disabled?: boolean;
  accessibilityLabel?: string;
};

export function SpatialButton({
  focusKey,
  className = '',
  children,
  onPress,
  disabled = false,
  accessibilityLabel,
}: SpatialButtonProps) {
  const { ref, focused, focusSelf } = useFocusable({
    focusKey,
    focusable: !disabled,
    accessibilityLabel,
    onEnterPress: () => {
      if (!disabled) onPress?.();
    },
  });

  return (
    <div
      ref={ref}
      role="button"
      aria-disabled={disabled}
      data-spatial-focus={focused ? 'true' : 'false'}
      className={`spatial-button ${focused ? 'is-focused' : ''} ${disabled ? 'is-disabled' : ''} ${className}`}
      onMouseEnter={() => !disabled && focusSelf()}
      onClick={() => !disabled && onPress?.()}
    >
      {typeof children === 'function' ? children(focused) : children}
    </div>
  );
}

export function useInitialFocus(focusKey: string, dependency?: unknown) {
  useEffect(() => {
    const id = window.setTimeout(() => {
      void setFocus(focusKey);
    }, 40);
    return () => window.clearTimeout(id);
  }, [focusKey, dependency]);
}

export function useSpatialGamepad(onBack: () => void, onShoulder?: (delta: -1 | 1) => void) {
  const previous = useRef<boolean[]>([]);
  const nextMoveAt = useRef(0);

  useEffect(() => {
    let raf = 0;

    const pressEnter = () => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      window.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }));
    };

    const poll = () => {
      const pad = navigator.getGamepads?.().find(Boolean);
      if (pad) {
        const buttons = pad.buttons.map((button) => button.pressed);
        const edge = (index: number) => buttons[index] && !previous.current[index];
        const now = performance.now();
        const x = pad.axes[0] ?? 0;
        const y = pad.axes[1] ?? 0;

        const left = buttons[14] || x < -0.64;
        const right = buttons[15] || x > 0.64;
        const up = buttons[12] || y < -0.64;
        const down = buttons[13] || y > 0.64;

        if (now >= nextMoveAt.current) {
          if (left) { void navigateByDirection('left'); nextMoveAt.current = now + 175; }
          else if (right) { void navigateByDirection('right'); nextMoveAt.current = now + 175; }
          else if (up) { void navigateByDirection('up'); nextMoveAt.current = now + 175; }
          else if (down) { void navigateByDirection('down'); nextMoveAt.current = now + 175; }
        }

        if (edge(0)) pressEnter();
        if (edge(1)) onBack();
        if (edge(4)) onShoulder?.(-1);
        if (edge(5)) onShoulder?.(1);
        previous.current = buttons;
      }
      raf = requestAnimationFrame(poll);
    };

    raf = requestAnimationFrame(poll);
    return () => cancelAnimationFrame(raf);
  }, [onBack, onShoulder]);
}
