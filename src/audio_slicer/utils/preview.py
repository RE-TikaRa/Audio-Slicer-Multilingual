import soundfile
import numpy as np
import matplotlib.pyplot as plt

from audio_slicer.utils.audioutil import AudioUtil

dark_theme_palette = {
    'primary': '#8ab4f7',
    'accent': 'orange',
    'page_background': '#202124',
    'figure_frame': '#404040',
    'figure_background': '#202020',
    'axis': '#A0A0A0',
    'title': '#e4e7eb',
    'grid': '#404040'
}
light_theme_palette = {
    'primary': '#1a73e8',
    'accent': 'orange',
    'page_background': '#f8f9fa',
    'figure_frame': '#B0B0B0',
    'figure_background': '#F0F0F0',
    'axis': '#505050',
    'title': '#4d5157',
    'grid': '#B0B0B0'
}


class SlicingPreview:
    def __init__(self,
                 filename: str,
                 sil_tags: list,
                 hop_size: int,
                 total_frames: int,
                 waveform_shape: int,
                 theme: str):
        self.filename = filename
        self.sil_tags = sil_tags
        self.hop_size = hop_size
        self.total_frames = total_frames
        self.waveform_shape = waveform_shape
        self.theme = theme
        ori_audio, ori_sr = soundfile.read(filename, dtype=np.float32)

        # Convert to mono if not
        if len(ori_audio.shape) > 1:
            ori_audio = ori_audio.T
            ori_audio = AudioUtil.to_mono(ori_audio)

        # Downsample audio before plotting due to performance issue
        target_sr = 6000
        self.target_sr = target_sr
        self.audio_samples = AudioUtil.resample(y=ori_audio, orig_sr=ori_sr, target_sr=target_sr, res_type="soxr_hq")

    def _apply_slice(self, begin, end):
        return [begin * self.hop_size,
                min(self.waveform_shape, end * self.hop_size)]

    def _get_ranges(self, sil_tags: list):
        if len(sil_tags) == 0:
            return []
        else:
            ranges = []
            if sil_tags[0][0] > 0:
                ranges.append(self._apply_slice(0, sil_tags[0][0]))
            for i in range(len(sil_tags) - 1):
                ranges.append(self._apply_slice(sil_tags[i][1], sil_tags[i + 1][0]))
            if sil_tags[-1][1] < self.total_frames:
                ranges.append(self._apply_slice(sil_tags[-1][1], self.total_frames))
            return ranges

    def _get_length_distribution(self):
        values = [0, 0, 0, 0, 0, 0, 0, 0]  # range 0-2 2-5 5-8 8-11 11-14 14-17 17-20 20+
        for length in self.length_list:
            if length[1] < 2:
                values[0] += 1
            elif length[1] < 5:
                values[1] += 1
            elif length[1] < 8:
                values[2] += 1
            elif length[1] < 11:
                values[3] += 1
            elif length[1] < 14:
                values[4] += 1
            elif length[1] < 17:
                values[5] += 1
            elif length[1] < 20:
                values[6] += 1
            else:
                values[7] += 1
        return values

    def _get_length_ranking_list(self):
        items = []
        values = []
        self.length_list.sort(key=lambda x: x[1])
        count = len(self.length_list)
        cropped_list = self.length_list if count <= 10 else self.length_list[count - 10:]
        for list_item in cropped_list:
            items.append(list_item[0])
            values.append(round(list_item[1], 3))
        return items, values

    def _plot_preview(self, preview_filename: str):
        time = np.arange(0, len(self.audio_samples)) * (1.0 / self.target_sr)

        palette = dark_theme_palette if self.theme == 'dark' else light_theme_palette
        plt.rcParams['toolbar'] = 'None'
        plt.figure(figsize=(10, 6))

        # Plot Waveform
        plt.subplot(211)
        plt.plot(time, self.audio_samples, color=palette['primary'])
        fig = plt.gcf()
        fig.set_facecolor(palette['page_background'])
        fig.tight_layout(pad=3, w_pad=2, h_pad=3)
        ax = plt.gca()
        ax.set_facecolor(palette['figure_background'])
        ax.spines['top'].set_color(palette['figure_frame'])
        ax.spines['bottom'].set_color(palette['figure_frame'])
        ax.spines['left'].set_color(palette['figure_frame'])
        ax.spines['right'].set_color(palette['figure_frame'])
        ax.tick_params(
            axis='x',
            color=palette['axis'],
            labelcolor=palette['axis']
        )
        ax.tick_params(
            axis='y',
            color=palette['axis'],
            labelcolor=palette['axis']
        )
        # plt.title(
        #     label='Audio WaveForm',
        #     fontdict={
        #         "color": palette['title']
        #     }
        # )
        plt.xlabel(
            xlabel="Time/s",
            fontdict={
                "color": palette['axis']
            }
        )
        plt.ylabel(
            ylabel="dB",
            fontdict={
                "color": palette['axis']
            }
        )
        plt.grid(
            color=palette['grid']
        )
        plt.autoscale(enable=True, axis='x', tight=True)
        plt.ylim((-1, 1))
        plt.yticks([-1, -0.707, -0.501, -0.355, -0.126, 0, 0.126, 0.355, 0.501, 0.707, 1],
                   ['0', '-3', '-6', '-9', '-18', '-INF', '-18', '-9', '-6', '-3', '0'])
        ranges = self._get_ranges(sil_tags=self.sil_tags)
        self.length_list = []
        for i in range(len(ranges)):
            start_pos = ranges[i][0] / 1000.  # Convert ms to s
            end_pos = ranges[i][1] / 1000.
            length = end_pos - start_pos
            self.length_list.append(('#' + str(i), length))  # Add length to list
            plt.annotate("#" + str(i),
                         xy=(start_pos, 1),
                         xycoords=("data", "axes fraction"),
                         color=palette['accent']
                         )
            plt.axvline(x=start_pos, color=palette['accent'])
            plt.axvline(x=end_pos, color=palette['accent'])

        # Plot Length Distribution
        plt.subplot(223)
        distribution_items = ["<2", "<5", "<8", "<11", "<14", "<17", "<20", ">=20"]
        # values = [1, 5, 7, 11, 13, 7, 5, 1]
        len_values = self._get_length_distribution()
        plt.ylim(0, max(len_values) / 0.9)
        plt.bar(distribution_items,
                len_values,
                color=palette['primary'])
        for a, b in zip(distribution_items, len_values):
            plt.text(a, b, b, ha='center', va='bottom', fontdict={
                "color": palette['title']
            })
        ax = plt.gca()
        ax.set_facecolor(palette['figure_background'])
        ax.spines['top'].set_color(palette['figure_frame'])
        ax.spines['bottom'].set_color(palette['figure_frame'])
        ax.spines['left'].set_color(palette['figure_frame'])
        ax.spines['right'].set_color(palette['figure_frame'])
        ax.tick_params(
            axis='x',
            color=palette['axis'],
            labelcolor=palette['axis']
        )
        ax.tick_params(
            axis='y',
            color=palette['axis'],
            labelcolor=palette['axis']
        )
        plt.title(
            label='Length Distribution',
            fontdict={
                "color": palette['title']
            }
        )

        # Plot Length Ranking List
        plt.subplot(224)
        # items = ["#5", "#1", "#6", "#8", "#12", "#7"]
        # values = [21, 28, 32, 36, 45, 51]
        ranking_items, ranking_values = self._get_length_ranking_list()
        plt.xlim(0, max(ranking_values) / 0.9)
        plt.barh(ranking_items, ranking_values, color=palette['primary'])
        for a, b in zip(ranking_items, ranking_values):
            plt.text(b, a, b, ha='left', va='center', fontdict={
                "color": palette['title']
            })
        ax = plt.gca()
        ax.set_facecolor(palette['figure_background'])
        ax.spines['top'].set_color(palette['figure_frame'])
        ax.spines['bottom'].set_color(palette['figure_frame'])
        ax.spines['left'].set_color(palette['figure_frame'])
        ax.spines['right'].set_color(palette['figure_frame'])
        ax.tick_params(
            axis='x',
            color=palette['axis'],
            labelcolor=palette['axis']
        )
        ax.tick_params(
            axis='y',
            color=palette['axis'],
            labelcolor=palette['axis']
        )
        plt.title(
            label='Length Ranking List',
            fontdict={
                "color": palette['title']
            }
        )
        plt.savefig(preview_filename, dpi=150)
        # plt.show()

    def save_plot(self, filename: str):
        self._plot_preview(filename)


if __name__ == "__main__":
    pass
    # showWaveForm("D:/测试/slicer测试音频/2009000334.wav")
    # showWaveForm("D:\\编曲学习\\小小\\小小（伊拾七干声）.wav")
    # showWaveForm("D:\\测试\\slicer测试音频\\Vocal (4).wav")
