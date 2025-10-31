/**
 * iOS Safari Modal Fix
 * Prevents modal freezing and scroll issues on iPhone/iPad
 */

(function() {
    'use strict';

    // Only apply fixes on iOS devices
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
                  (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

    if (!isIOS) {
        return; // Exit if not iOS
    }

    let scrollPosition = 0;

    // Handle modal show event
    document.addEventListener('show.bs.modal', function() {
        // Save current scroll position
        scrollPosition = window.pageYOffset || document.documentElement.scrollTop;

        // Apply fixed positioning with preserved scroll position
        document.body.style.position = 'fixed';
        document.body.style.top = `-${scrollPosition}px`;
        document.body.style.width = '100%';
    });

    // Handle modal hide event
    document.addEventListener('hide.bs.modal', function() {
        // Remove fixed positioning
        document.body.style.position = '';
        document.body.style.top = '';
        document.body.style.width = '';

        // Restore scroll position
        window.scrollTo(0, scrollPosition);
    });

    // Prevent background scroll when touching inside modal
    document.addEventListener('touchmove', function(e) {
        if (document.body.classList.contains('modal-open')) {
            const target = e.target;
            const modal = target.closest('.modal-dialog');

            // Allow scrolling inside modal, prevent elsewhere
            if (!modal) {
                e.preventDefault();
            }
        }
    }, { passive: false });

})();
