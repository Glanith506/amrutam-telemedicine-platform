// DOM tests use synthetic fixtures, not live patient data.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { JSDOM } = require('jsdom');

const html = readFileSync('index.html', 'utf8');
const source = readFileSync('app.js', 'utf8');

const doctor = {
  id: 'doctor-1',
  name: 'Dr. Test Doctor',
  specialty: 'Ayurveda',
  fee_paise: 50000
};

const slot = {
  id: 'slot-1',
  starts_at: '2030-01-01T10:00:00Z',
  ends_at: '2030-01-01T10:30:00Z'
};

function setup(role = 'patient', overrides = {}) {
  const dom = new JSDOM(html, {
    url: 'http://localhost:8000',
    runScripts: 'outside-only',
    pretendToBeVisual: true
  });

  const w = dom.window;
  const calls = [];

  const profile = {
    id: role === 'doctor' ? 'doctor-1' : 'account-1',
    name: 'Test User',
    email: 'ui-test@example.com',
    role,
    mfa_enabled: role !== 'patient'
  };

  w.scrollTo = () => {};
  w.AbortSignal = global.AbortSignal;

  w.HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };

  w.HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };

  w.fetch = async (path, options = {}) => {
    calls.push({
      path,
      method: options.method || 'GET',
      headers: options.headers,
      body: options.body ? JSON.parse(options.body) : undefined
    });

    const custom = overrides[`${options.method || 'GET'} ${path}`];

    if (custom) {
      return new Response(JSON.stringify(custom.data), {
        status: custom.status || 200
      });
    }

    let data;

    if (path === '/health/ready') {
      data = { status: 'ready' };
    } else if (path.startsWith('/doctors?')) {
      data = [doctor];
    } else if (path.includes('/slots?')) {
      data = [slot];
    } else if (path === '/auth/login') {
      data = {
        access_token: 'synthetic-test-token',
        token_type: 'bearer'
      };
    } else if (path === '/me') {
      data = profile;
    } else if (path === '/auth/register') {
      data = { id: 'new-patient', role: 'patient' };
    } else if (path.startsWith('/consultations?')) {
      data = [];
    } else if (path === '/consultations') {
      data = { id: 'consultation-1', status: 'booked' };
    } else if (path === '/doctors/me/slots') {
      data = { id: 'new-slot' };
    } else if (path === '/admin/analytics') {
      data = {
        patients: 4,
        doctors: 2,
        consultations_by_status: { completed: 3, booked: 1 }
      };
    } else if (path.startsWith('/admin/audit?')) {
      data = [];
    } else if (path === '/admin/doctors') {
      data = { doctor_id: 'provisioned' };
    } else {
      throw new Error('Unexpected endpoint: ' + path);
    }

    return new Response(JSON.stringify(data), { status: 200 });
  };

  w.eval(source);

  return {
    dom,
    w,
    d: w.document,
    calls,
    close: async () => {
      await new Promise(resolve => setTimeout(resolve, 30));
      dom.window.close();
    }
  };
}

async function until(fn) {
  for (let i = 0; i < 100; i++) {
    if (fn()) return;
    await new Promise(resolve => setTimeout(resolve, 10));
  }

  throw new Error('DOM expectation timed out');
}

async function signin(ctx) {
  ctx.d.querySelector('#account-button').click();
  ctx.d.querySelector('#auth-email').value = 'ui-test@example.com';
  ctx.d.querySelector('#auth-password').value = 'SyntheticPassword123!';
  ctx.d.querySelector('#auth-form').requestSubmit();

  await until(
    () => ctx.d.querySelector('#account-label').textContent === 'Test User'
  );
}

test('public directory renders response fields and converts rupees to paise', async () => {
  const c = setup();

  try {
    await until(() => c.d.querySelector('.doctor-name'));

    assert.equal(
      c.d.querySelector('.doctor-name').textContent,
      doctor.name
    );
    assert.match(c.d.querySelector('.fee').textContent, /500/);

    c.d.querySelector(
      '#public-header [data-action="doctors"]'
    ).click();

    c.d.querySelector('[name="specialty"]').value = 'Ayurveda';
    c.d.querySelector('[name="fee"]').value = '600';
    c.d.querySelector('#doctor-filter').requestSubmit();

    await until(
      () => c.calls.some(x => x.path.includes('max_fee_paise=60000'))
    );
  } finally {
    await c.close();
  }
});

test('patient booking sends token and idempotency key', async () => {
  const c = setup();

  try {
    await signin(c);
    await until(() => c.d.querySelector('[data-doctor]'));

    c.d.querySelector('[data-doctor]').click();
    await until(() => c.d.querySelector('[data-slot]'));

    c.d.querySelector('[data-slot]').click();
    c.d.querySelector('#booking-form').requestSubmit();

    await until(
      () => c.calls.some(
        x => x.path === '/consultations' && x.method === 'POST'
      )
    );

    const request = c.calls.find(
      x => x.path === '/consultations' && x.method === 'POST'
    );

    assert.equal(
      request.headers.Authorization,
      'Bearer synthetic-test-token'
    );
    assert.ok(request.headers['Idempotency-Key']);
    assert.equal(request.body.slot_id, 'slot-1');
    assert.equal(c.w.localStorage.length, 0);
    assert.equal(c.w.sessionStorage.length, 0);
  } finally {
    await c.close();
  }
});

test('registration returns to sign-in without retaining the password', async () => {
  const c = setup();

  try {
    c.d.querySelector('#account-button').click();
    c.d.querySelector('#register-tab').click();

    c.d.querySelector('#auth-name').value = 'New User';
    c.d.querySelector('#auth-email').value = 'new@example.com';
    c.d.querySelector('#auth-password').value =
      'NewSyntheticPassword123!';

    c.d.querySelector('#auth-form').requestSubmit();

    await until(() => c.calls.some(x => x.path === '/auth/register'));
    await until(() => c.d.querySelector('#auth-otp'));

    assert.equal(
      c.d.querySelector('#auth-email').value,
      'new@example.com'
    );
    assert.equal(c.d.querySelector('#auth-password').value, '');
  } finally {
    await c.close();
  }
});

test('login errors remain visible without creating a session', async () => {
  const c = setup('patient', {
    'POST /auth/login': {
      status: 401,
      data: { detail: 'Invalid credentials' }
    }
  });

  try {
    c.d.querySelector('#account-button').click();
    c.d.querySelector('#auth-email').value = 'ui-test@example.com';
    c.d.querySelector('#auth-password').value = 'wrong';
    c.d.querySelector('#auth-form').requestSubmit();

    await until(() => c.d.querySelector('#auth-form .error'));

    assert.match(
      c.d.querySelector('#auth-form .error').textContent,
      /Invalid credentials/
    );
    assert.equal(
      c.d.querySelector('#account-label').textContent,
      'Sign in'
    );
  } finally {
    await c.close();
  }
});

test('doctor publishes a slot with UTC timestamps', async () => {
  const c = setup('doctor');

  try {
    await signin(c);
    c.d.querySelector('[data-page="availability"]').click();

    c.d.querySelector('#slot-start').value = '2030-01-01T10:00';
    c.d.querySelector('#slot-end').value = '2030-01-01T10:30';
    c.d.querySelector('#availability-form').requestSubmit();

    await until(
      () => c.calls.some(
        x => x.path === '/doctors/me/slots' && x.method === 'POST'
      )
    );

    const request = c.calls.find(
      x => x.path === '/doctors/me/slots' && x.method === 'POST'
    );

    assert.ok(request.body.starts_at.endsWith('Z'));
    assert.ok(request.body.ends_at.endsWith('Z'));
    assert.ok(request.headers['Idempotency-Key']);
  } finally {
    await c.close();
  }
});

test('admin sees analytics and provisions doctor fees in paise', async () => {
  const c = setup('admin');

  try {
    await signin(c);
    c.d.querySelector('[data-page="admin"]').click();

    await until(() => c.d.querySelector('#status-bars .bar-fill'));

    c.d.querySelector('#doctor-user-id').value = 'target-user';
    c.d.querySelector('#doctor-specialty').value = 'Ayurveda';
    c.d.querySelector('#doctor-fee').value = '750';
    c.d.querySelector('#doctor-create-form').requestSubmit();

    await until(() => c.calls.some(x => x.path === '/admin/doctors'));

    assert.equal(
      c.calls.find(x => x.path === '/admin/doctors').body.fee_paise,
      75000
    );
  } finally {
    await c.close();
  }
});

test('untrusted doctor names render as text rather than markup', async () => {
  const unsafeName = '<img src=x onerror=alert(1)>';

  const c = setup('patient', {
    'GET /doctors?limit=12&offset=0': {
      data: [{ ...doctor, name: unsafeName }]
    }
  });

  try {
    await until(() => c.d.querySelector('.doctor-name'));

    assert.equal(
      c.d.querySelector('.doctor-name').textContent,
      unsafeName
    );
    assert.equal(c.d.querySelector('.doctor-name img'), null);
  } finally {
    await c.close();
  }
});

test('visitors see public navigation without private account pages', async () => {
  const c = setup();

  try {
    await until(() => c.d.querySelector('#public-header'));

    assert.equal(
      c.d.querySelector('[data-page="appointments"]'),
      null
    );
    assert.equal(
      c.d.querySelector('[data-page="settings"]'),
      null
    );

    const signIn = c.d.querySelector(
      '#public-header [data-action="signin"]'
    );

    assert.ok(signIn);
    signIn.click();

    await until(() => c.d.querySelector('#auth-form'));
    assert.ok(c.d.querySelector('#auth-email'));
  } finally {
    await c.close();
  }
});

test('public Create account button opens registration', async () => {
  const c = setup();

  try {
    await until(() => c.d.querySelector('#public-header'));

    c.d.querySelector(
      '#public-header [data-action="signup"]'
    ).click();

    assert.ok(c.d.querySelector('#auth-name'));
    assert.match(
      c.d.querySelector('#modal-title').textContent,
      /care starts/
    );
  } finally {
    await c.close();
  }
});

test('homepage search carries specialty and fee to the directory', async () => {
  const c = setup();

  try {
    await until(() => c.d.querySelector('#overview-search'));

    c.d.querySelector(
      '#overview-search [name="specialty"]'
    ).value = 'Ayurveda';

    c.d.querySelector(
      '#overview-search [name="fee"]'
    ).value = '550';

    c.d.querySelector('#overview-search').requestSubmit();

    await until(
      () => c.calls.some(x => x.path.includes('max_fee_paise=55000'))
    );

    assert.equal(
      c.d.querySelector('#doctor-filter [name="specialty"]').value,
      'Ayurveda'
    );
  } finally {
    await c.close();
  }
});