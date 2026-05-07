/**
 * UI Enhancements JS
 * Centralized loader and progress bar management
 */

const UI = {
    progressInterval: null,
    progress: 0,

    /**
     * Show Global Spinner Loader
     */
    showLoader: function() {
        const loader = document.getElementById('global-loader');
        if (loader) {
            loader.classList.add('show');
        }
    },

    /**
     * Hide Global Spinner Loader
     */
    hideLoader: function() {
        const loader = document.getElementById('global-loader');
        if (loader) {
            loader.classList.remove('show');
        }
    },

    /**
     * Start Top Progress Bar
     */
    startProgress: function() {
        const bar = document.getElementById('top-progress-bar');
        if (!bar) return;

        this.progress = 0;
        bar.style.width = '0%';
        bar.style.opacity = '1';
        bar.style.display = 'block';

        if (this.progressInterval) clearInterval(this.progressInterval);

        this.progressInterval = setInterval(() => {
            if (this.progress < 90) {
                this.progress += Math.random() * 10;
                bar.style.width = this.progress + '%';
            }
        }, 300);
    },

    /**
     * Stop and Complete Top Progress Bar
     */
    stopProgress: function() {
        const bar = document.getElementById('top-progress-bar');
        if (!bar) return;

        clearInterval(this.progressInterval);
        bar.style.width = '100%';
        
        setTimeout(() => {
            bar.style.opacity = '0';
            setTimeout(() => {
                bar.style.width = '0%';
                bar.style.display = 'none';
            }, 300);
        }, 200);
    },

    /**
     * Initialize Page Transitions
     */
    initPageTransitions: function() {
        // Intercept all links for progress bar and transitions
        document.addEventListener('click', (e) => {
            const link = e.target.closest('a');
            if (link) {
                const href = link.getAttribute('href');
                const target = link.getAttribute('target');
                
                // Only for internal links that don't open in new tab
                if (href && 
                    !href.startsWith('#') && 
                    !href.startsWith('javascript:') && 
                    !target && 
                    !e.ctrlKey && 
                    !e.metaKey &&
                    link.hostname === window.location.hostname) {
                    
                    e.preventDefault();
                    document.body.classList.add('fade-out');
                    this.startProgress();
                    
                    setTimeout(() => {
                        window.location.href = href;
                    }, 300);
                }
            }
        });

        // Add fade-in to body on load
        document.body.classList.add('page-transition-fade');
    },

    /**
     * Helper to load data with skeletons
     * @param {string} skeletonId - ID of skeleton element to hide
     * @param {string} contentId - ID of content element to show
     * @param {Function} fetchPromise - Function returning a promise that fetches data
     */
    loadWithSkeleton: async function(skeletonId, contentId, fetchPromise) {
        const skeleton = document.getElementById(skeletonId);
        const content = document.getElementById(contentId);

        if (skeleton) skeleton.style.display = 'block';
        if (content) content.style.display = 'none';

        try {
            await fetchPromise();
        } finally {
            if (skeleton) skeleton.style.display = 'none';
            if (content) {
                content.style.display = 'block';
                content.classList.add('content-fade-in');
            }
        }
    }
};

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    UI.initPageTransitions();

    // Intercept form submissions
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', () => {
            UI.startProgress();
            UI.showLoader();
        });
    });
});

// Stop progress when page is fully loaded
window.addEventListener('load', () => {
    UI.stopProgress();
});
