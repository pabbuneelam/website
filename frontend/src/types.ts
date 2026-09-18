// Mirrors slate/models.py and the shapes returned by slate/api.py.

export interface AttributeDef {
  slot: string
  label: string
  requires: string
  guardrail: string
}

export interface Game {
  game_id: number
  home: string
  away: string
  tipoff: string
}

export interface SlatePlayer {
  player_id: number
  name: string
  team: string
  opponent: string
  salary: number | null
}

export interface Slate {
  date: string
  slots: string[]
  games: Game[]
  players: SlatePlayer[]
}

export interface Selection {
  slot: string
  player_id: number
}

export interface BuildPayload {
  creator: string
  selections: Selection[]
}

export interface Rating {
  slot: string
  label: string
  player_id: number
  player_name: string
  rating: number
  value: number | null
  percentile: number
  salary: number | null
  note: string
  pts: number
  reb: number
  ast: number
  fantasy: number
}

export interface Card {
  card_id: string
  creator: string
  date: string
  ovr: number
  contract: number
  ratings: Rating[]
  void: boolean
  void_reason: string
}
