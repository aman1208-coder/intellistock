import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import {
  ApiError,
  listManagedUsers,
  register,
  resetManagedUserPassword,
  setManagedUserActive,
  type ManagedUser,
} from './api';

type MemberForm = {
  username: string;
  email: string;
  password: string;
};

type OneTimeCredential = {
  username: string;
  email: string;
  password: string;
};

const EMPTY_FORM: MemberForm = { username: '', email: '', password: '' };
const PASSWORD_ALPHABET = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%_-';

function randomIndex(maximum: number): number {
  const limit = Math.floor(0x100000000 / maximum) * maximum;
  const value = new Uint32Array(1);
  do {
    crypto.getRandomValues(value);
  } while (value[0] >= limit);
  return value[0] % maximum;
}

function generateStrongPassword(): string {
  const groups = [
    'abcdefghijkmnopqrstuvwxyz',
    'ABCDEFGHJKLMNPQRSTUVWXYZ',
    '23456789',
    '!@#$%_-',
  ];
  const characters = groups.map((group) => group[randomIndex(group.length)]);
  while (characters.length < 24) {
    characters.push(PASSWORD_ALPHABET[randomIndex(PASSWORD_ALPHABET.length)]);
  }
  for (let index = characters.length - 1; index > 0; index -= 1) {
    const swapIndex = randomIndex(index + 1);
    [characters[index], characters[swapIndex]] = [characters[swapIndex], characters[index]];
  }
  return characters.join('');
}

function explainError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return error instanceof Error ? error.message : 'The request could not be completed.';
  }
  if (error.status === 401) {
    return 'Your session expired. Please sign in again.';
  }
  if (error.status === 403) {
    return 'Only an administrator can manage member accounts.';
  }
  if (error.status === 409) {
    return 'That username or email is already in use.';
  }
  if (error.status === 422) {
    return error.message || 'Check the account details and password requirements.';
  }
  return error.message || 'The request could not be completed.';
}

export default function MembersPanel({ currentUsername }: { currentUsername: string }) {
  const [members, setMembers] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyUserId, setBusyUserId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<MemberForm>(EMPTY_FORM);
  const [showPassword, setShowPassword] = useState(false);
  const [oneTimeCredential, setOneTimeCredential] = useState<OneTimeCredential | null>(null);
  const [copyMessage, setCopyMessage] = useState('');

  useEffect(() => {
    let active = true;
    listManagedUsers()
      .then((result) => {
        if (active) setMembers(result);
      })
      .catch((requestError: unknown) => {
        if (active) setError(explainError(requestError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const closeDialog = () => {
    setDialogOpen(false);
    setForm(EMPTY_FORM);
    setShowPassword(false);
    setOneTimeCredential(null);
    setCopyMessage('');
    setError('');
  };

  const createMember = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    try {
      const created = await register(form.email, form.username, form.password);
      setMembers((current) => [...current, created].sort((a, b) => a.id - b.id));
      setOneTimeCredential({
        username: created.username,
        email: created.email,
        password: form.password,
      });
      setForm(EMPTY_FORM);
    } catch (requestError) {
      setError(explainError(requestError));
    }
  };

  const updateMemberStatus = async (member: ManagedUser) => {
    setBusyUserId(member.id);
    setError('');
    try {
      const updated = await setManagedUserActive(member.id, !member.is_active);
      setMembers((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (requestError) {
      setError(explainError(requestError));
    } finally {
      setBusyUserId(null);
    }
  };

  const resetPassword = async (member: ManagedUser) => {
    if (!window.confirm(`Reset the password for ${member.username}?`)) return;
    setBusyUserId(member.id);
    setError('');
    try {
      const result = await resetManagedUserPassword(member.id);
      setForm(EMPTY_FORM);
      setCopyMessage('');
      setOneTimeCredential({
        username: member.username,
        email: member.email,
        password: result.temporary_password,
      });
      setDialogOpen(true);
    } catch (requestError) {
      setError(explainError(requestError));
    } finally {
      setBusyUserId(null);
    }
  };

  const copyTemporaryPassword = async () => {
    if (!oneTimeCredential) return;
    try {
      await navigator.clipboard.writeText(oneTimeCredential.password);
      setCopyMessage('Temporary password copied.');
    } catch {
      setCopyMessage('Clipboard unavailable. Select and copy the password manually.');
    }
  };

  return (
    <motion.section
      className="glass-panel"
      id="members"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="section-heading">
        <div>
          <span className="eyebrow">Account administration</span>
          <h2>Members</h2>
        </div>
        <button type="button" className="primary" onClick={() => { setError(''); setDialogOpen(true); }}>
          Create member
        </button>
      </div>

      {error ? <p className="api-error-inline" role="alert">{error}</p> : null}
      {loading ? <p className="empty-state">Loading accounts…</p> : null}
      {!loading && members.length === 0 ? <p className="empty-state">No accounts are available.</p> : null}
      {members.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Username</th><th>Email</th><th>Role</th><th>Active</th><th>Created</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {members.map((member) => (
                <tr key={member.id}>
                  <td>{member.username}</td>
                  <td>{member.email}</td>
                  <td>{member.role}</td>
                  <td>{member.is_active ? 'Active' : 'Inactive'}</td>
                  <td>{new Date(member.created_at).toLocaleString()}</td>
                  <td>
                    <div className="button-row">
                      <button
                        type="button"
                        disabled={busyUserId === member.id || (member.username === currentUsername && member.is_active)}
                        title={member.username === currentUsername ? 'You cannot deactivate your own account.' : undefined}
                        onClick={() => void updateMemberStatus(member)}
                      >
                        {member.username === currentUsername && member.is_active
                          ? 'Cannot deactivate self'
                          : member.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                      <button
                        type="button"
                        disabled={busyUserId === member.id}
                        onClick={() => void resetPassword(member)}
                      >
                        Reset password
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <AnimatePresence>
        {dialogOpen ? (
          <motion.div
            className="modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={(event) => {
              if (event.target === event.currentTarget) closeDialog();
            }}
          >
            <motion.div
              className="modal-card"
              role="dialog"
              aria-modal="true"
              aria-labelledby="member-dialog-title"
              initial={{ opacity: 0, scale: 0.92 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              onClick={(event) => event.stopPropagation()}
            >
              <div className="modal-header">
                <div>
                  <span className="eyebrow">Administrator only</span>
                  <h3 id="member-dialog-title">{oneTimeCredential ? 'One-time credentials' : 'Create member account'}</h3>
                </div>
                <button type="button" aria-label="Close dialog" onClick={closeDialog}>Close</button>
              </div>

              {error ? <p className="api-error-inline" role="alert">{error}</p> : null}
              {oneTimeCredential ? (
                <div className="member-credentials">
                  <p role="alert">Save these credentials now. The password will not be shown again after you close this dialog.</p>
                  <p><strong>Username:</strong> {oneTimeCredential.username}</p>
                  <p><strong>Email:</strong> {oneTimeCredential.email}</p>
                  <label>
                    Temporary password
                    <input type="text" readOnly value={oneTimeCredential.password} />
                  </label>
                  <button type="button" onClick={() => void copyTemporaryPassword()}>Copy password</button>
                  {copyMessage ? <p role="status">{copyMessage}</p> : null}
                </div>
              ) : (
                <form className="member-create-form" onSubmit={(event) => void createMember(event)}>
                  <label>
                    Username
                    <input
                      autoComplete="off"
                      minLength={3}
                      maxLength={32}
                      pattern="[A-Za-z0-9._-]+"
                      value={form.username}
                      onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))}
                      required
                    />
                  </label>
                  <label>
                    Email
                    <input
                      type="email"
                      autoComplete="off"
                      maxLength={255}
                      value={form.email}
                      onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
                      required
                    />
                  </label>
                  <label>
                    Initial password (at least 12 characters)
                    <input
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="new-password"
                      minLength={12}
                      maxLength={72}
                      value={form.password}
                      onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
                      required
                    />
                  </label>
                  <div className="button-row">
                    <button type="button" onClick={() => setShowPassword((visible) => !visible)}>
                      {showPassword ? 'Hide password' : 'Show password'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setForm((current) => ({ ...current, password: generateStrongPassword() }))}
                    >
                      Generate strong password
                    </button>
                    <button type="submit" className="primary">Create member</button>
                  </div>
                </form>
              )}
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.section>
  );
}
