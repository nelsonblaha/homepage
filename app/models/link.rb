class Link < ActiveRecord::Base
  attr_accessible :description, :title, :url
  has_many :taggings, foreign_key: :item_id, dependent: :destroy
  has_many :tags, through: :taggings
end
