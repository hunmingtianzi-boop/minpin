let activeLocks = 0;
let previousOverflow = "";
let previousPaddingRight = "";

/**
 * Lock page scrolling without letting the disappearing scrollbar shift the UI.
 * Multiple dialogs can overlap; original styles return after the final unlock.
 */
export function lockBodyScroll() {
  const body = document.body;

  if (activeLocks === 0) {
    previousOverflow = body.style.overflow;
    previousPaddingRight = body.style.paddingRight;

    const scrollbarWidth = Math.max(
      0,
      window.innerWidth - document.documentElement.clientWidth,
    );
    if (scrollbarWidth > 0) {
      const currentPaddingRight =
        Number.parseFloat(window.getComputedStyle(body).paddingRight) || 0;
      body.style.paddingRight = `${currentPaddingRight + scrollbarWidth}px`;
    }
    body.style.overflow = "hidden";
  }

  activeLocks += 1;
  let released = false;

  return () => {
    if (released) return;
    released = true;
    activeLocks = Math.max(0, activeLocks - 1);

    if (activeLocks === 0) {
      body.style.overflow = previousOverflow;
      body.style.paddingRight = previousPaddingRight;
    }
  };
}
