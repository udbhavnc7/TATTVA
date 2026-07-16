/**
 * Smoke test — confirms Vitest + Testing Library setup works correctly.
 */
import { render, screen } from '@testing-library/react'

describe('Test setup smoke test', () => {
    it('renders a React element and finds it in the document', () => {
        render(<div>Tattva is ready</div>)
        expect(screen.getByText('Tattva is ready')).toBeInTheDocument()
    })
})
