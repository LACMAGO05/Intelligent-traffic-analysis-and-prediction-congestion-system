/**
 * Traffik Loading Experience Manager
 */

const Loader = {
    el: null,

    init() {
        this.el = document.getElementById('global-loader');
        this.bindForms();
    },

    show() {
        if (this.el) {
            this.el.classList.remove('hidden');
            // Force reflow
            this.el.offsetHeight;
            this.el.classList.add('show');
        }
    },

    hide() {
        if (this.el) {
            this.el.classList.remove('show');
            setTimeout(() => {
                if (!this.el.classList.contains('show')) {
                    this.el.classList.add('hidden');
                }
            }, 300);
        }
    },

    /**
     * Bind to all forms to show loading state on submission
     */
    bindForms() {
        document.querySelectorAll('form').forEach(form => {
            form.addEventListener('submit', (e) => {
                // If the form is already submitting, prevent double submission
                if (form.dataset.submitting === 'true') {
                    e.preventDefault();
                    return;
                }

                const submitBtn = form.querySelector('[type="submit"]');
                if (submitBtn) {
                    this.setButtonLoading(submitBtn);
                }

                // Show global loader for non-AJAX forms (full page reload)
                // For AJAX forms, the developer should call Loader.show()/hide() manually or use handleRequest
                if (!form.hasAttribute('data-ajax')) {
                    this.show();
                }

                form.dataset.submitting = 'true';
            });
        });
    },

    setButtonLoading(btn) {
        btn.disabled = true;
        btn.classList.add('btn-loading');
        
        // Optional: change text if data-loading-text is provided
        const originalText = btn.innerHTML;
        const loadingText = btn.dataset.loadingText || 'Processing...';
        
        // Store original text to revert if needed (e.g. on error)
        btn.dataset.originalText = originalText;
        
        // We use a span for the text if we want to preserve layout but hide text
        // In our CSS .btn-loading makes text transparent, so we don't necessarily need to change it
        // but it's good for accessibility
        if (btn.dataset.loadingText) {
             btn.innerHTML = `<span>${loadingText}</span>`;
        }
    },

    revertButton(btn) {
        btn.disabled = false;
        btn.classList.remove('btn-loading');
        if (btn.dataset.originalText) {
            btn.innerHTML = btn.dataset.originalText;
        }
    },

    /**
     * Wrap an async request with loading states
     * @param {Function} asyncFunc - The async function to execute
     * @returns {Promise}
     */
    async handleRequest(asyncFunc) {
        this.show();
        try {
            const result = await asyncFunc();
            return result;
        } catch (error) {
            console.error('Request failed:', error);
            // Optionally show a toast error here
            this.showError(error.message || 'An unexpected error occurred.');
            throw error;
        } finally {
            this.hide();
        }
    },

    showError(message) {
        // Simple alert for now, can be replaced with a nice Toast component
        alert(message);
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    Loader.init();
});

// Export for use in other scripts
window.TraffikLoader = Loader;
