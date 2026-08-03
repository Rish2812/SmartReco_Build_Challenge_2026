// Minimal client-side auth helper. Token stored in localStorage for this demo app
// (a production build would use an httpOnly cookie instead).

const Auth = {
  getToken() { return localStorage.getItem('smartreco_token'); },
  getUser() {
    const raw = localStorage.getItem('smartreco_user');
    return raw ? JSON.parse(raw) : null;
  },
  setSession(token, user) {
    localStorage.setItem('smartreco_token', token);
    localStorage.setItem('smartreco_user', JSON.stringify(user));
  },
  clearSession() {
    localStorage.removeItem('smartreco_token');
    localStorage.removeItem('smartreco_user');
  },
  async authedFetch(url, options = {}) {
    const token = this.getToken();
    const headers = Object.assign({}, options.headers, {
      'Authorization': token ? `Bearer ${token}` : '',
    });
    return fetch(url, Object.assign({}, options, { headers }));
  },
};

function renderNavAuthState() {
  const user = Auth.getUser();
  const authBox = document.getElementById('authBox');
  const adminLink = document.getElementById('adminLink');
  if (!authBox) return;

  if (user) {
    authBox.innerHTML = `<span style="margin-right:12px; font-size:14px;">${user.email}</span><button id="logoutBtn">Log out</button>`;
    document.getElementById('logoutBtn').addEventListener('click', () => {
      Auth.clearSession();
      window.location.href = '/';
    });
    if (adminLink && user.role === 'admin') adminLink.style.display = 'inline';
  }
}

document.addEventListener('DOMContentLoaded', renderNavAuthState);
