// js/footer.js — Clean, Professional Application Footer

document.addEventListener('DOMContentLoaded', () => {
    // Prevent duplicate footer injection
    if (document.querySelector('.app-footer')) return;

    // Ensure body takes full height for sticky footer bottom alignment
    if (!document.body.classList.contains('d-flex')) {
        document.body.style.display = 'flex';
        document.body.style.flexDirection = 'column';
        document.body.style.minHeight = '100vh';
    }

    const footer = document.createElement('footer');
    footer.id = 'contact';
    footer.className = 'app-footer mt-auto';
    footer.innerHTML = `
        <div class="container">
            <div class="app-footer-container">
                <div class="app-footer-contact">
                    <div class="app-footer-item">
                        <i class="fa-solid fa-envelope"></i>
                        <a href="mailto:shameela5qts@gmail.com">shameela5qts@gmail.com</a>
                    </div>
                    <div class="app-footer-item">
                        <i class="fa-solid fa-phone"></i>
                        <a href="tel:6383649156">6383649156</a>
                    </div>
                </div>
                <div class="app-footer-credit">
                    Created by <span>Shameela &amp; Team</span>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(footer);
});
