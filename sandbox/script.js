// Smooth scrolling for navigation links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Navbar scroll effect
window.addEventListener('scroll', () => {
    const navbar = document.querySelector('.navbar');
    if (window.scrollY > 100) {
        navbar.style.boxShadow = '0 5px 20px rgba(0,0,0,0.15)';
    } else {
        navbar.style.boxShadow = '0 2px 5px rgba(0,0,0,0.1)';
    }
});

// Interactive feature cards animation on load
const featureCards = document.querySelectorAll('.feature-card');
let cardCount = 0;

function animateFeatures() {
    if (cardCount < featureCards.length) {
        const card = featureCards[cardCount];
        card.style.opacity = '1';
        card.style.transform = 'translateY(0)';
        cardCount++;
        setTimeout(animateFeatures, 300);
    }
}

// Apply initial animations after a slight delay
setTimeout(animateFeatures, 500);

// Add click handlers to buttons
document.querySelectorAll('.btn').forEach(button => {
    button.addEventListener('click', function(e) {
        if (!this.dataset.action || this.dataset.action === 'default') {
            const btnText = this.textContent.trim();
            const confirmMsg = `Do you want to ${btnText}?`;
            if (confirm(confirmMsg)) {
                console.log(`${btnText} action triggered`);
            }
        }
    });
});

// Console message on page load
console.log('🚀 Landing page loaded successfully!');
console.log('Start exploring our features and get started!');
