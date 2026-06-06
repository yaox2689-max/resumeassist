import { reactive } from 'vue'

const TOKEN_KEY = 'capymock-token'
const USER_KEY = 'capymock-user'

const state = reactive({
  token: localStorage.getItem(TOKEN_KEY) || '',
  user: JSON.parse(localStorage.getItem(USER_KEY) || 'null'),
})

export function useAuth() {
  function isLoggedIn() {
    return !!state.token
  }

  function getUser() {
    return state.user
  }

  function getToken() {
    return state.token
  }

  function setAuth(token, user) {
    state.token = token
    state.user = user
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  }

  function logout() {
    state.token = ''
    state.user = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  return { state, isLoggedIn, getUser, getToken, setAuth, logout }
}
