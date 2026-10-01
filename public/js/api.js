const Api = (() => {
  function token() { return localStorage.getItem('leica_token'); }

  async function req(path, { method = 'GET', body, isForm } = {}) {
    const headers = {};
    if (!isForm) headers['Content-Type'] = 'application/json';
    if (token()) headers['Authorization'] = 'Bearer ' + token();

    const resp = await fetch('/api' + path, {
      method,
      headers,
      body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
    });

    if (resp.status === 204) return null;
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || `Error ${resp.status}`);
    return data;
  }

  return {
    get: (p) => req(p),
    post: (p, body) => req(p, { method: 'POST', body }),
    put: (p, body) => req(p, { method: 'PUT', body }),
    del: (p) => req(p, { method: 'DELETE' }),
    postForm: (p, formData) => req(p, { method: 'POST', body: formData, isForm: true }),
    token,
    setToken: (t) => localStorage.setItem('leica_token', t),
    clearToken: () => localStorage.removeItem('leica_token'),
  };
})();
