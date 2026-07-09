import { describe, expect, it } from 'vitest'

import { displayTodoExecutor, todoGlyph, todoTone } from './todo.js'

describe('todoGlyph', () => {
  it('uses fixed-width ASCII markers so the active row does not render wide or emoji-like', () => {
    expect(todoGlyph('completed')).toBe('[x]')
    expect(todoGlyph('in_progress')).toBe('[>]')
    expect(todoGlyph('pending')).toBe('[ ]')
    expect(todoGlyph('cancelled')).toBe('[-]')
  })
})

describe('todoTone', () => {
  it('keeps todo status rows neutral instead of red/green', () => {
    expect(todoTone('completed')).toBe('dim')
    expect(todoTone('cancelled')).toBe('dim')
    expect(todoTone('pending')).toBe('body')
    expect(todoTone('in_progress')).toBe('active')
  })
})

describe('displayTodoExecutor', () => {
  it('accepts compact lowercase tokens and normalizes case/whitespace', () => {
    expect(displayTodoExecutor('codex')).toBe('codex')
    expect(displayTodoExecutor('  Claude  ')).toBe('claude')
    expect(displayTodoExecutor('gemini-cli')).toBe('gemini-cli')
  })

  it('aliases hermes-agent to the short display form', () => {
    expect(displayTodoExecutor('hermes-agent')).toBe('hermes')
    expect(displayTodoExecutor('Hermes-Agent')).toBe('hermes')
    expect(displayTodoExecutor('hermes')).toBe('hermes')
  })

  it('drops invalid, hostile, or credential-shaped values entirely', () => {
    expect(displayTodoExecutor(undefined)).toBeNull()
    expect(displayTodoExecutor(123)).toBeNull()
    expect(displayTodoExecutor('')).toBeNull()
    expect(displayTodoExecutor('two words')).toBeNull()
    expect(displayTodoExecutor('a'.repeat(33))).toBeNull()
    expect(displayTodoExecutor('https://evil.example/agent')).toBeNull()
    expect(displayTodoExecutor('[claude](https://evil.example)')).toBeNull()
    expect(displayTodoExecutor('<at id=ou_x>bot</at>')).toBeNull()
    expect(displayTodoExecutor('sk-' + 'a'.repeat(24))).toBeNull()
    expect(displayTodoExecutor('ghp_' + 'b'.repeat(24))).toBeNull()
    expect(displayTodoExecutor('xoxb-slack-token')).toBeNull()
  })
})
