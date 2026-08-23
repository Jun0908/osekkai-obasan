import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import JudgeDemoClient from './judge-demo-client';


describe('JudgeDemoClient', () => {
  it('completes the hobby Story without Google login or a runtime API request', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('backend unavailable'));
    render(<JudgeDemoClient />);

    expect(screen.getByText('Googleログイン不要')).toBeInTheDocument();
    expect(screen.queryByTestId('judge-demo-event')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '音楽' }));
    const initialCards = screen.getAllByTestId('judge-demo-event');
    expect(initialCards).toHaveLength(3);
    expect(within(initialCards[0]).getByText(/口笛演奏入門/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '最初から会話はちょっと…' }));
    expect(screen.getByText(/交流そのものではなく、会話から始まる負担/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /口笛演奏入門.*に行ってみる/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Event後のCheck-inへ' }));
    fireEvent.click(screen.getByRole('button', { name: '活動のあとなら話しやすかった' }));

    expect(screen.getByText('次の距離感が変わりました')).toBeInTheDocument();
    expect(screen.getByText(/行かない理由まで聞いて/)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it('shows that a tired user is not given Event candidates', () => {
    render(<JudgeDemoClient />);
    fireEvent.click(screen.getByRole('button', { name: /STORY 2.*今日は疲れている/ }));
    fireEvent.click(screen.getByRole('button', { name: '今日は疲れた' }));

    expect(screen.queryByTestId('judge-demo-event')).not.toBeInTheDocument();
    expect(screen.getByText(/空きは元気の証拠ちゃう/)).toBeInTheDocument();
    expect(screen.getByText(/Calendarの空きより本人の『疲れた』を優先/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '元気な日に一回だけ聞いて' }));
    expect(screen.getByText(/断られたら追わない/)).toBeInTheDocument();
  });

  it('reorders the continuity Story toward a recurring Event', () => {
    render(<JudgeDemoClient />);
    fireEvent.click(screen.getByRole('button', { name: /STORY 3.*一回の参加を/ }));
    fireEvent.click(screen.getByRole('button', { name: '次の候補を見せて' }));
    expect(within(screen.getAllByTestId('judge-demo-event')[0]).getByText('Night Run vol.7')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '同じ人にまた会える方がいい' }));
    const reorderedCards = screen.getAllByTestId('judge-demo-event');
    expect(within(reorderedCards[0]).getByText(/口笛演奏入門/)).toBeInTheDocument();
    expect(within(reorderedCards[0]).getByText('順位変更')).toBeInTheDocument();
    expect(within(reorderedCards[0]).getByText('経路未記録')).toBeInTheDocument();
  });

  it('resets only the selected local Story state', () => {
    render(<JudgeDemoClient />);
    fireEvent.click(screen.getByRole('button', { name: 'ヨガ' }));
    expect(screen.getAllByTestId('judge-demo-event')).toHaveLength(3);
    fireEvent.click(screen.getByRole('button', { name: '最初から見る' }));
    expect(screen.queryByTestId('judge-demo-event')).not.toBeInTheDocument();
  });
});
