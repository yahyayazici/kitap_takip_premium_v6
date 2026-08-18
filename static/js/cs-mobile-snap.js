(function () {
    "use strict";

    /* touch-action:manipulation already removes the 300ms delay.
       Do not synthesize click on pointerdown: that double-toggles the
       hamburger / dropdown (open then immediately close) on iOS. */
})();
