import { useEffect, useState } from 'react'
import { ApiError, getCollection } from '../api'
import type { Card } from '../types'
import CardResult from './CardResult'

export default function Collection({ creator }: { creator: string }) {
  const [cards, setCards] = useState<Card[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    if (!creator.trim()) {
      setError('enter a creator name first')
      return
    }
    setLoading(true)
    setError(null)
    getCollection(creator)
      .then(setCards)
      .catch((err: unknown) => {
        const message = err instanceof ApiError ? err.message : 'failed to load collection'
        setError(message)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (creator.trim()) load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="collection">
      <div className="collection__toolbar">
        <button onClick={load} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
      {error && <p className="error-banner">{error}</p>}
      {cards && cards.length === 0 && <p>No cards yet — build one on the Build tab.</p>}
      {cards && cards.length > 0 && (
        <div className="collection__list">
          {cards.map((c) => (
            <CardResult key={c.card_id} card={c} />
          ))}
        </div>
      )}
    </div>
  )
}
