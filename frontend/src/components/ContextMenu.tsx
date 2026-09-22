import * as React from 'react';
import { ContextMenu as ContextMenuPrimitive } from '@base-ui/react/context-menu';

const ContextMenuStateContext = React.createContext<{
  open: boolean;
  setOpen: (open: boolean) => void;
}>({ open: false, setOpen: () => {} });

export function ContextMenu({
  children,
  open: controlledOpen,
  onOpenChange: controlledOnOpenChange,
  ...props
}: ContextMenuPrimitive.Root.Props) {
  const [uncontrolledOpen, setUncontrolledOpen] = React.useState(false);
  const open = controlledOpen ?? uncontrolledOpen;

  const handleOpenChange = React.useCallback(
    (nextOpen: boolean, eventDetails: ContextMenuPrimitive.Root.ChangeEventDetails) => {
      setUncontrolledOpen(nextOpen);
      controlledOnOpenChange?.(nextOpen, eventDetails);
    },
    [controlledOnOpenChange]
  );

  const setOpen = React.useCallback((nextOpen: boolean) => {
    setUncontrolledOpen(nextOpen);
  }, []);

  return (
    <ContextMenuStateContext.Provider value={{ open, setOpen }}>
      <ContextMenuPrimitive.Root
        open={open}
        onOpenChange={handleOpenChange}
        {...props}
      >
        {children}
      </ContextMenuPrimitive.Root>
    </ContextMenuStateContext.Provider>
  );
}

export function ContextMenuTrigger({
  className,
  onContextMenuCapture,
  ...props
}: ContextMenuPrimitive.Trigger.Props & { onContextMenuCapture?: React.MouseEventHandler<HTMLDivElement> }) {
  const { open, setOpen } = React.useContext(ContextMenuStateContext);

  const handleContextMenuCapture = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;

    if (e.shiftKey) {
      if (open) setOpen(false);
      e.stopPropagation();
      return;
    }

    const selection = window.getSelection();
    if (selection && selection.toString().trim().length > 0) {
      if (open) setOpen(false);
      e.stopPropagation();
      return;
    }

    if (
      target.closest(
        'img, video, audio, a, input, textarea, [contenteditable="true"], .rich-editor, .search-bar, .attachment-item'
      )
    ) {
      if (open) setOpen(false);
      e.stopPropagation();
      return;
    }

    if (open) {
      setOpen(false);
      e.stopPropagation();
      return;
    }

    onContextMenuCapture?.(e);
  };

  return (
    <ContextMenuPrimitive.Trigger
      className={className}
      onContextMenuCapture={handleContextMenuCapture}
      {...props}
    />
  );
}

export function ContextMenuContent({
  className,
  align = 'start',
  alignOffset = 4,
  side = 'right',
  sideOffset = 0,
  ...props
}: ContextMenuPrimitive.Popup.Props &
  Pick<
    ContextMenuPrimitive.Positioner.Props,
    'align' | 'alignOffset' | 'side' | 'sideOffset'
  >) {
  return (
    <ContextMenuPrimitive.Portal>
      <ContextMenuPrimitive.Positioner
        className="isolate z-50 outline-none"
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
      >
        <ContextMenuPrimitive.Popup
          className={`custom-context-menu ${className || ''}`}
          {...props}
        />
      </ContextMenuPrimitive.Positioner>
    </ContextMenuPrimitive.Portal>
  );
}

export function ContextMenuItem({
  className,
  variant = 'default',
  ...props
}: ContextMenuPrimitive.Item.Props & {
  variant?: 'default' | 'destructive';
}) {
  return (
    <ContextMenuPrimitive.Item
      data-variant={variant}
      className={`custom-context-item ${className || ''}`}
      {...props}
    />
  );
}

export function ContextMenuSeparator({
  className,
  ...props
}: ContextMenuPrimitive.Separator.Props) {
  return (
    <ContextMenuPrimitive.Separator
      className={`custom-context-separator ${className || ''}`}
      {...props}
    />
  );
}
