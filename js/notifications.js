// js/notifications.js
document.addEventListener('DOMContentLoaded', async () => {
    // Wait slightly to ensure Auth and DB are initialized
    setTimeout(initNotifications, 500);
});

async function initNotifications() {
    const user = Auth.getCurrentUser();
    if (!user) return;
    
    // Inject Notification Bell into Navbar
    const navUl = document.querySelector('.navbar-nav.ms-auto');
    if (!navUl) return;
    
    // Avoid duplicate injections
    if (document.getElementById('notifDropdown')) return;

    const notifLi = document.createElement('li');
    notifLi.className = 'nav-item dropdown me-3';
    notifLi.innerHTML = `
        <a class="nav-link position-relative" href="#" id="notifDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
            <i class="fa-solid fa-bell fs-5 text-charcoal"></i>
            <span id="notifBadge" class="position-absolute top-25 start-75 translate-middle badge rounded-pill bg-danger d-none" style="font-size: 0.65em;">
                0
            </span>
        </a>
        <ul class="dropdown-menu dropdown-menu-end shadow border-0" aria-labelledby="notifDropdown" id="notifList" style="width: 320px; max-height: 400px; overflow-y: auto;">
            <li class="text-center p-3 text-secondary-gray small">Loading notifications...</li>
        </ul>
    `;
    
    // Insert before the Welcome message
    const welcomeLi = Array.from(navUl.children).find(li => li.innerText.includes('Welcome'));
    if (welcomeLi) {
        navUl.insertBefore(notifLi, welcomeLi);
    } else {
        navUl.appendChild(notifLi);
    }
    
    // Listen to Firebase Realtime Database
    if (user.role === 'admin') {
        DB.onAdminNotifications(renderNotifications);
    } else if (user.role === 'owner') {
        DB.onOwnerNotifications(user.uid, renderNotifications);
    }
}

function renderNotifications(notifications) {
    // Sort by createdAt desc
    notifications.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
    
    const unreadCount = notifications.filter(n => n.status === 'unread').length;
    const badge = document.getElementById('notifBadge');
    
    if (unreadCount > 0) {
        badge.textContent = unreadCount;
        badge.classList.remove('d-none');
    } else {
        badge.classList.add('d-none');
    }
    
    const listEl = document.getElementById('notifList');
    if (notifications.length === 0) {
        listEl.innerHTML = '<li class="text-center p-3 text-secondary-gray small">No notifications yet.</li>';
        return;
    }
    
    let html = `
        <li>
            <div class="dropdown-header d-flex justify-content-between align-items-center fw-bold">
                Notifications
            </div>
        </li>
        <li><hr class="dropdown-divider m-0"></li>
    `;

    notifications.forEach(n => {
        const isUnread = n.status === 'unread';
        let bgClass = isUnread ? 'bg-light' : '';
        let borderClass = isUnread ? 'border-start border-4 border-primary' : 'border-start border-4 border-transparent';
        
        let icon = '<i class="fa-solid fa-bell text-primary mt-1"></i>';
        if (n.type === 'vehicle_approved') {
            icon = '<i class="fa-solid fa-circle-check text-success mt-1"></i>';
            if (isUnread) borderClass = 'border-start border-4 border-success';
        }
        if (n.type === 'vehicle_rejected') {
            icon = '<i class="fa-solid fa-circle-xmark text-danger mt-1"></i>';
            if (isUnread) borderClass = 'border-start border-4 border-danger';
        }
        if (n.type === 'vehicle_approval') {
            icon = '<i class="fa-solid fa-car-side text-warning mt-1"></i>';
            if (isUnread) borderClass = 'border-start border-4 border-warning';
        }
        
        const timeStr = formatTimeAgo(new Date(n.createdAt));
        
        html += `
            <li>
                <a class="dropdown-item py-2 px-3 ${bgClass} ${borderClass} border-bottom text-wrap" href="#" onclick="handleNotifClick(event, '${n.id}', '${n.type}')" style="white-space: normal;">
                    <div class="d-flex gap-2">
                        <div>${icon}</div>
                        <div class="flex-grow-1">
                            <p class="mb-0 fw-bold small ${isUnread ? 'text-dark' : 'text-secondary-gray'}">${n.title || 'Notification'}</p>
                            <p class="mb-0 small text-secondary-gray" style="line-height: 1.3;">${n.message}</p>
                            <small class="text-muted" style="font-size: 11px;">${timeStr}</small>
                        </div>
                    </div>
                </a>
            </li>
        `;
    });
    
    listEl.innerHTML = html;
}

window.handleNotifClick = async function(e, notifId, type) {
    e.preventDefault();
    // Mark as read
    try {
        await DB.markNotificationRead(notifId);
    } catch(err) {
        console.error("Failed to mark notification as read", err);
    }
    
    const user = Auth.getCurrentUser();
    
    // Routing logic
    if (user.role === 'admin') {
        if (type === 'vehicle_approval') {
            window.location.href = 'vehicles.html';
        } else {
            window.location.href = 'dashboard.html';
        }
    } else {
        if (type === 'vehicle_approved' || type === 'vehicle_rejected') {
            window.location.href = 'manage-vehicles.html';
        } else {
            window.location.href = 'dashboard.html';
        }
    }
};

function formatTimeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000);
    let interval = seconds / 31536000;
    if (interval > 1) return Math.floor(interval) + " years ago";
    interval = seconds / 2592000;
    if (interval > 1) return Math.floor(interval) + " months ago";
    interval = seconds / 86400;
    if (interval > 1) return Math.floor(interval) + " days ago";
    interval = seconds / 3600;
    if (interval > 1) return Math.floor(interval) + " hours ago";
    interval = seconds / 60;
    if (interval > 1) return Math.floor(interval) + " minutes ago";
    return Math.floor(seconds) + " seconds ago";
}
