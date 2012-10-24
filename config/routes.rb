Blaha::Application.routes.draw do
  resources :taggings
  	match '/new_tagging_for_link', to: 'taggings#new_for_link'

  resources :tags

  resources :links

  devise_for :users

  get "welcome/index"

  root :to => 'welcome#index'
end
