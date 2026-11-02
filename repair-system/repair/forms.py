"""表单：报修单的创建与编辑都用这一个 ModelForm，字段和校验规则跟着模型走，不重复写。"""

from django import forms

from .models import RepairOrder


class RepairOrderForm(forms.ModelForm):
    """报修单表单"""

    class Meta:
        model = RepairOrder
        # 白名单：状态、报修人、处理人都不让用户填，由后端决定
        fields = ['title', 'category', 'location', 'priority', 'description', 'image']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '一句话描述故障'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：3 号教学楼 402'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 5, 'placeholder': '故障现象、出现时间、影响范围'}
            ),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean_title(self) -> str:
        """标题去掉首尾空格，避免「 空调坏了 」这种存进去的数据"""
        title = self.cleaned_data['title'].strip()
        if len(title) < 4:
            raise forms.ValidationError('标题太短了，至少 4 个字')
        return title
